package com.logix.poc;

import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import java.net.URI;
import java.net.http.*;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@org.springframework.test.annotation.DirtiesContext(classMode = org.springframework.test.annotation.DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {"sandbox.enabled=true", "sandbox.token=synthetic-sandbox-token-with-at-least-32-chars", "sandbox.namespace=test-sandbox"})
class SandboxIntegrationTest extends CommandIntegrationTest {
    static final String TOKEN = "synthetic-sandbox-token-with-at-least-32-chars";
    static final String XML = """
        <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" targetNamespace="urn:synthetic">
        <process id="sb_parallel" isExecutable="true"><startEvent id="s"/><parallelGateway id="fork"/>
        <userTask id="a"/><userTask id="b"/><parallelGateway id="join"/><endEvent id="e"/>
        <sequenceFlow id="f1" sourceRef="s" targetRef="fork"/><sequenceFlow id="f2" sourceRef="fork" targetRef="a"/>
        <sequenceFlow id="f3" sourceRef="fork" targetRef="b"/><sequenceFlow id="f4" sourceRef="a" targetRef="join"/>
        <sequenceFlow id="f5" sourceRef="b" targetRef="join"/><sequenceFlow id="f6" sourceRef="join" targetRef="e"/>
        </process></definitions>
        """;
    String hash(String value) throws Exception {
        return java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
    }
    Map<String,Object> deployPayload(String xml) throws Exception {
        return Map.of("xml", xml, "xml_hash", hash(xml), "basis_hash", "a".repeat(64),
            "model_version_id", 1, "process_id", 1,
            "assignments", Map.of("a", List.of("pms:1"), "b", List.of("pms:2")));
    }
    com.fasterxml.jackson.databind.JsonNode http(String method, String path, Object payload, String token, int status) throws Exception {
        var json = new com.fasterxml.jackson.databind.ObjectMapper();
        var builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/sandbox/v1" + path)).header("Authorization", "Bearer " + token);
        if (payload != null) builder.header("Content-Type", "application/json").method(method, HttpRequest.BodyPublishers.ofString(json.writeValueAsString(payload)));
        else builder.method(method, HttpRequest.BodyPublishers.noBody());
        var response = HttpClient.newHttpClient().send(builder.build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(status, response.statusCode(), response.body());
        return json.readTree(response.body());
    }
    com.fasterxml.jackson.databind.JsonNode send(String action, String target, Map<String,Object> payload) throws Exception {
        return http("POST", "/commands", request(action, target, payload), TOKEN, 200).get("result");
    }
    @Test void sandbox_has_distinct_authentication() throws Exception {
        http("GET", "/info", null, System.getenv("FLOWABLE_POC_TOKEN"), 401);
        assertEquals("test-sandbox", http("GET", "/info", null, TOKEN, 200).get("namespace").asText());
    }
    @Test void sandbox_parallel_tasks_use_exact_actor_and_replay() throws Exception {
        var d = send("SB_DEPLOY", "model:1", deployPayload(XML));
        var r = request("SB_START", d.get("definition_id").asText(), Map.of("business_key", "sandbox:" + UUID.randomUUID(),
            "context", Map.of("process_id", 1, "model_version_id", 1, "instance_id", 1)));
        var receipt = http("POST", "/commands", r, TOKEN, 200);
        assertEquals(receipt, http("POST", "/commands", r, TOKEN, 200));
        assertEquals(409, assertThrows(PocException.class, () -> commands.execute(new PocDtos.CommandRequest(r.command_id(), r.action(), "different", r.payload()))).status());
        String id = receipt.get("result").get("instance_id").asText();
        var view = http("GET", "/instances/" + id, null, TOKEN, 200);
        assertEquals(2, view.get("tasks").size());
        for (var t : view.get("tasks")) {
            String actor = t.get("candidates").get(0).asText();
            http("POST", "/commands", request("SB_COMPLETE", t.get("task_id").asText(), Map.of("actor", "pms:999")), TOKEN, 403);
            send("SB_COMPLETE", t.get("task_id").asText(), Map.of("actor", actor));
        }
        var done = http("GET", "/instances/" + id, null, TOKEN, 200);
        assertEquals("COMPLETED", done.get("status").asText());
        assertEquals(2, done.get("history_tasks").size());
    }
    @Test void unsafe_xml_rejected_before_deployment() throws Exception {
        for (String xml : List.of(XML.replace("<userTask id=\"a\"/>", "<scriptTask id=\"a\"><script>bad()</script></scriptTask>"),
                XML.replace("<process ", "<process xmlns:f=\"http://flowable.org/bpmn\" f:async=\"true\" "),
                "<!DOCTYPE x [<!ENTITY x SYSTEM 'file:///secret'>]>" + XML)) {
            http("POST", "/commands", request("SB_DEPLOY", "model:1", deployPayload(xml)), TOKEN, 400);
        }
    }
}
