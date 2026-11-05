package com.logix.poc;

import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import java.util.concurrent.*;
import org.flowable.engine.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CommandIntegrationTest {
    @Autowired CommandService commands;
    @Autowired FixtureService fixtures;
    @Autowired CommandRepository receipts;
    @Autowired EventRepository events;
    @Autowired ProcessEngine engine;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager tx;
    @org.springframework.boot.test.web.server.LocalServerPort int port;

    @Test void invalid_token_cannot_replay() throws Exception {
        var receipt = deploy();
        var url = java.net.URI.create("http://127.0.0.1:" + port + "/poc/v1/commands/" + receipt.command_id());
        var response = java.net.http.HttpClient.newHttpClient().send(java.net.http.HttpRequest.newBuilder(url)
            .header("Authorization", "Bearer invalid").GET().build(), java.net.http.HttpResponse.BodyHandlers.ofString());
        assertEquals(401, response.statusCode());
        assertFalse(response.body().contains("deployment_id"));
    }

    @Test void http_rejects_unknown_command_fields() throws Exception {
        var body = "{\"command_id\":\"" + UUID.randomUUID() + "\",\"action\":\"DEPLOY\",\"target\":\"serial\",\"payload\":{},\"unknown\":true}";
        var req = java.net.http.HttpRequest.newBuilder(java.net.URI.create("http://127.0.0.1:" + port + "/poc/v1/commands"))
            .header("Authorization", "Bearer " + System.getenv("FLOWABLE_POC_TOKEN")).header("Content-Type", "application/json")
            .POST(java.net.http.HttpRequest.BodyPublishers.ofString(body)).build();
        assertEquals(400, java.net.http.HttpClient.newHttpClient().send(req, java.net.http.HttpResponse.BodyHandlers.ofString()).statusCode());
    }

    PocDtos.CommandRequest request(String action, String target, Map<String,Object> payload) {
        return new PocDtos.CommandRequest(UUID.randomUUID(), action, target, payload);
    }
    PocDtos.CommandReceipt deploy() {
        return commands.execute(request("DEPLOY", "serial", Map.of("bpmn_sha256", fixtures.hash("serial"))));
    }
    PocDtos.CommandRequest start(String definition) {
        return request("START", definition, Map.of("business_key", "poc:" + UUID.randomUUID() + ":serial",
            "context", Map.of("source", "POC_FIXTURE", "process_id", 910001, "model_version_id", 910001), "variables", Map.of()));
    }
    String started() { return commands.execute(start(deploy().result().get("definition_id").toString())).result().get("instance_id").toString(); }

    @Test void deploy_fixed_fixture_and_reuse_hash() {
        var a = deploy(); var b = deploy();
        assertEquals(a.result(), b.result());
        assertNotNull(a.result().get("deployment_id"));
        assertEquals(fixtures.hash("serial"), a.result().get("bpmn_sha256"));
    }
    @Test void reject_arbitrary_resource_or_hash() {
        assertThrows(PocException.class, () -> commands.execute(request("DEPLOY", "../../anything", Map.of("bpmn_sha256", "x"))));
        assertThrows(PocException.class, () -> commands.execute(request("DEPLOY", "serial", Map.of("bpmn_sha256", "x"))));
    }
    java.util.List<Map<String,Object>> allEvents() {
        var out = new ArrayList<Map<String,Object>>();
        long cursor = 0;
        while (true) {
            var page = events.after(cursor, 500); out.addAll(page.events());
            if (!page.has_more()) return out;
            cursor = page.next_after_id();
        }
    }
    @Test void serial_claim_complete() {
        String id = started();
        var task = engine.getTaskService().createTaskQuery().processInstanceId(id).singleResult();
        commands.execute(request("CLAIM", task.getId(), Map.of("actor", "poc-applicant")));
        commands.execute(request("COMPLETE", task.getId(), Map.of("actor", "poc-applicant")));
        assertNull(engine.getRuntimeService().createProcessInstanceQuery().processInstanceId(id).singleResult());
        assertNotNull(engine.getHistoryService().createHistoricProcessInstanceQuery().processInstanceId(id).finished().singleResult());
        var rows = allEvents().stream().filter(e -> id.equals(e.get("engine_instance_id"))).toList();
        assertTrue(rows.stream().anyMatch(e -> "TASK_COMPLETED".equals(e.get("type"))));
        assertTrue(rows.stream().anyMatch(e -> "PROCESS_COMPLETED".equals(e.get("type"))));
        assertTrue(rows.stream().allMatch(e -> e.get("definition_id") != null));
        assertTrue(rows.stream().anyMatch(e -> e.get("context").toString().contains("910001")));
    }
    @Test void same_command_replays_exact_receipt() {
        var r = start(deploy().result().get("definition_id").toString());
        assertEquals(commands.execute(r), commands.execute(r));
    }
    @Test void same_id_different_action_target_payload_conflicts() {
        var r = request("DEPLOY", "serial", Map.of("bpmn_sha256", fixtures.hash("serial")));
        commands.execute(r);
        for (var changed : List.of(new PocDtos.CommandRequest(r.command_id(), "START", r.target(), r.payload()),
                new PocDtos.CommandRequest(r.command_id(), r.action(), "parallel-signoff", r.payload()),
                new PocDtos.CommandRequest(r.command_id(), r.action(), r.target(), Map.of("bpmn_sha256", "changed")))) {
            assertEquals(409, assertThrows(PocException.class, () -> commands.execute(changed)).status());
        }
    }
    @Test void concurrent_start_same_command_creates_one_instance() throws Exception {
        var r = start(deploy().result().get("definition_id").toString());
        try (var pool = Executors.newFixedThreadPool(2)) {
            var gate = new CountDownLatch(1);
            Callable<PocDtos.CommandReceipt> work = () -> { gate.await(); return commands.execute(r); };
            var a = pool.submit(work); var b = pool.submit(work); gate.countDown();
            assertEquals(a.get(30, TimeUnit.SECONDS), b.get(30, TimeUnit.SECONDS));
        }
        assertEquals(1, engine.getHistoryService().createHistoricProcessInstanceQuery().processInstanceBusinessKey(r.payload().get("business_key").toString()).count());
    }
    @Test void different_command_same_business_key_conflicts() {
        var r = start(deploy().result().get("definition_id").toString()); commands.execute(r);
        var changed = new PocDtos.CommandRequest(UUID.randomUUID(), r.action(), r.target(), r.payload());
        assertEquals(409, assertThrows(PocException.class, () -> commands.execute(changed)).status());
        assertTrue(receipts.find(changed.command_id()).isEmpty());
    }
    @Test void event_listener_failure_rolls_back_engine_and_receipt() {
        String id = started();
        String task = engine.getTaskService().createTaskQuery().processInstanceId(id).singleResult().getId();
        var r = request("COMPLETE", task, Map.of("actor", "poc-applicant"));
        jdbc.execute("CREATE OR REPLACE FUNCTION poc_test_reject() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.payload->>'type'='TASK_COMPLETED' THEN RAISE EXCEPTION 'injected event failure'; END IF; RETURN NEW; END $$");
        jdbc.execute("CREATE TRIGGER poc_test_reject BEFORE INSERT ON poc_event FOR EACH ROW EXECUTE FUNCTION poc_test_reject()");
        try {
            assertThrows(RuntimeException.class, () -> commands.execute(r));
            assertNotNull(engine.getTaskService().createTaskQuery().taskId(task).singleResult());
            assertTrue(receipts.find(r.command_id()).isEmpty());
            assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM poc_event WHERE payload->>'engine_instance_id'=? AND payload->>'type'='TASK_COMPLETED'", Integer.class, id));
        } finally { jdbc.execute("DROP TRIGGER poc_test_reject ON poc_event"); jdbc.execute("DROP FUNCTION poc_test_reject()"); }
        assertNotNull(commands.execute(r));
    }
    @Test void events_page_replay_is_stable() {
        started();
        var a = events.after(0, 2); var b = events.after(0, 2);
        assertEquals(a, b); assertEquals(2, a.events().size()); assertTrue(a.has_more());
        assertTrue(events.after(a.next_after_id(), 2).events().stream().allMatch(e -> ((Number)e.get("journal_id")).longValue() > a.next_after_id()));
        assertThrows(PocException.class, () -> events.after(-1, 2));
        assertThrows(PocException.class, () -> events.after(0, 501));
    }
    @Test void event_cursor_does_not_skip_uncommitted_lower_id() throws Exception {
        long before = allEvents().stream().mapToLong(e -> ((Number)e.get("journal_id")).longValue()).max().orElse(0);
        var written = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(2)) {
            var first = pool.submit(() -> new TransactionTemplate(tx).execute(s -> {
                events.append(new HashMap<>(Map.of("type", "TEST_CURSOR_A"))); written.countDown();
                try { assertTrue(release.await(5, TimeUnit.SECONDS)); } catch (InterruptedException e) { throw new RuntimeException(e); }
                return 1;
            }));
            assertTrue(written.await(5, TimeUnit.SECONDS));
            var second = pool.submit(() -> new TransactionTemplate(tx).execute(s -> { events.append(new HashMap<>(Map.of("type", "TEST_CURSOR_B"))); return 1; }));
            assertThrows(TimeoutException.class, () -> second.get(200, TimeUnit.MILLISECONDS));
            var mid = events.after(before, 500); assertTrue(mid.events().stream().noneMatch(e -> e.get("type").toString().startsWith("TEST_CURSOR")));
            release.countDown(); first.get(5, TimeUnit.SECONDS); second.get(5, TimeUnit.SECONDS);
            assertEquals(2, events.after(mid.next_after_id(), 500).events().stream().filter(e -> e.get("type").toString().startsWith("TEST_CURSOR")).count());
        } finally { release.countDown(); }
    }
}
