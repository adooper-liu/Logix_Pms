package com.logix.poc;

import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class WorkflowIntegrationTest extends CommandIntegrationTest {
    String launch(String fixture, Map<String,Object> variables) {
        var d = commands.execute(request("DEPLOY", fixture, Map.of("bpmn_sha256", fixtures.hash(fixture))));
        var s = start(d.result().get("definition_id").toString());
        var payload = new HashMap<>(s.payload()); payload.put("variables", variables);
        return commands.execute(new PocDtos.CommandRequest(s.command_id(), s.action(), s.target(), payload)).result().get("instance_id").toString();
    }
    void complete(String task, String actor) { commands.execute(request("COMPLETE", task, Map.of("actor", actor))); }
    java.util.List<org.flowable.task.api.Task> tasks(String id) { return engine.getTaskService().createTaskQuery().processInstanceId(id).list(); }
    void parallelBranches(String id) {
        for (var t : tasks(id)) complete(t.getId(), t.getTaskDefinitionKey().equals("quality") ? "poc-quality" : "poc-plan");
    }
    @Test void parallel_join_waits_for_both_branches() {
        String id = launch("parallel-signoff", Map.of());
        assertEquals(2, tasks(id).size());
        var q = tasks(id).stream().filter(t -> t.getTaskDefinitionKey().equals("quality")).findFirst().orElseThrow();
        complete(q.getId(), "poc-quality");
        assertEquals(1, tasks(id).size()); assertEquals("plan", tasks(id).getFirst().getTaskDefinitionKey());
        parallelBranches(id); assertEquals(2, tasks(id).size());
        assertTrue(tasks(id).stream().allMatch(t -> t.getTaskDefinitionKey().equals("review")));
        assertNotEquals(tasks(id).get(0).getId(), tasks(id).get(1).getId());
    }
    @Test void all_reviewers_required() {
        String id = launch("parallel-signoff", Map.of()); parallelBranches(id);
        var reviews = tasks(id); assertEquals(2, reviews.size());
        complete(reviews.getFirst().getId(), reviews.getFirst().getAssignee()); assertEquals(1, tasks(id).size());
        assertNotNull(engine.getRuntimeService().createProcessInstanceQuery().processInstanceId(id).singleResult());
        var last = tasks(id).getFirst(); complete(last.getId(), last.getAssignee());
        assertNull(engine.getRuntimeService().createProcessInstanceQuery().processInstanceId(id).singleResult());
    }
    @Test void message_before_timer_completes_once() throws Exception {
        String id = launch("message-timer", Map.of("waitDuration", "PT2S"));
        commands.execute(request("MESSAGE", id, Map.of("message_name", "PocResponse")));
        assertEquals(409, assertThrows(PocException.class, () -> commands.execute(request("MESSAGE", id, Map.of("message_name", "PocResponse")))).status());
        awaitDone(id);
        assertEquals("MESSAGE", engine.getHistoryService().createHistoricVariableInstanceQuery().processInstanceId(id).variableName("outcome").singleResult().getValue());
        Thread.sleep(2500);
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM poc_event WHERE payload->>'engine_instance_id'=? AND payload->>'type'='PROCESS_COMPLETED'", Integer.class, id));
    }
    @Test void timer_without_message_completes_timeout() throws Exception {
        String id = launch("message-timer", Map.of("waitDuration", "PT2S")); awaitDone(id);
        assertEquals("TIMEOUT", engine.getHistoryService().createHistoricVariableInstanceQuery().processInstanceId(id).variableName("outcome").singleResult().getValue());
    }
    void awaitDone(String id) throws Exception {
        long deadline = System.nanoTime() + 30_000_000_000L;
        while (engine.getRuntimeService().createProcessInstanceQuery().processInstanceId(id).singleResult() != null && System.nanoTime() < deadline) Thread.sleep(100);
        assertNotNull(engine.getHistoryService().createHistoricProcessInstanceQuery().processInstanceId(id).finished().singleResult());
    }
    @Test void instance_http_exposes_real_timer_due_and_history_completion() throws Exception {
        String id = launch("message-timer", Map.of("waitDuration", "PT2S"));
        var expected = engine.getManagementService().createTimerJobQuery().processInstanceId(id).singleResult().getDuedate().toInstant();
        var http = java.net.http.HttpClient.newHttpClient();
        var req = java.net.http.HttpRequest.newBuilder(java.net.URI.create("http://127.0.0.1:" + port + "/poc/v1/instances/" + id))
            .header("Authorization", "Bearer " + System.getenv("FLOWABLE_POC_TOKEN")).GET().build();
        var json = new com.fasterxml.jackson.databind.ObjectMapper();
        var running = json.readTree(http.send(req, java.net.http.HttpResponse.BodyHandlers.ofString()).body());
        assertTrue(running.hasNonNull("timer_due_at"));
        assertEquals(expected, java.time.OffsetDateTime.parse(running.get("timer_due_at").asText()).toInstant());
        assertTrue(running.get("completed_at").isNull());
        awaitDone(id);
        var done = json.readTree(http.send(req, java.net.http.HttpResponse.BodyHandlers.ofString()).body());
        assertEquals(engine.getHistoryService().createHistoricProcessInstanceQuery().processInstanceId(id).singleResult().getEndTime().toInstant(),
            java.time.OffsetDateTime.parse(done.get("completed_at").asText()).toInstant());
        assertFalse(java.time.OffsetDateTime.parse(done.get("completed_at").asText()).toInstant().isBefore(expected));
    }
    @Test void suspend_resume_and_cancel() {
        String id = launch("serial", Map.of()); String task = tasks(id).getFirst().getId();
        commands.execute(request("SUSPEND", id, Map.of()));
        assertEquals(409, assertThrows(PocException.class, () -> complete(task, "poc-applicant")).status());
        commands.execute(request("RESUME", id, Map.of())); complete(task, "poc-applicant");
        String cancel = launch("parallel-signoff", Map.of());
        commands.execute(request("CANCEL", cancel, Map.of())); assertTrue(tasks(cancel).isEmpty());
        assertNotNull(engine.getHistoryService().createHistoricProcessInstanceQuery().processInstanceId(cancel).singleResult().getDeleteReason());
    }
    @Test void wrong_candidate_unknown_message_and_unknown_variable_rejected() {
        String id = launch("serial", Map.of()); String task = tasks(id).getFirst().getId();
        assertEquals(403, assertThrows(PocException.class, () -> complete(task, "poc-plan")).status());
        assertNotNull(engine.getTaskService().createTaskQuery().taskId(task).singleResult());
        String wait = launch("message-timer", Map.of("waitDuration", "PT60S"));
        assertEquals(400, assertThrows(PocException.class, () -> commands.execute(request("MESSAGE", wait, Map.of("message_name", "unknown")))).status());
        assertThrows(PocException.class, () -> launch("serial", Map.of("arbitraryClass", "x")));
        commands.execute(request("CANCEL", wait, Map.of()));
    }
}
