package com.logix.poc;

import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.util.Map;
import org.flowable.engine.ProcessEngine;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class IsolationConfigTest {
    @LocalServerPort int port;
    @Autowired ApplicationContext context;
    @Autowired ProcessEngine engine;

    @Test void every_route_requires_machine_token() throws Exception {
        var client = HttpClient.newHttpClient();
        for (String path : new String[]{"health", "info", "fixtures", "events"}) {
            var uri = URI.create("http://127.0.0.1:" + port + "/poc/v1/" + path);
            assertEquals(401, client.send(HttpRequest.newBuilder(uri).GET().build(), HttpResponse.BodyHandlers.ofString()).statusCode());
            assertEquals(401, client.send(HttpRequest.newBuilder(uri).header("Authorization", "Bearer wrong").GET().build(), HttpResponse.BodyHandlers.ofString()).statusCode());
        }
        var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/poc/v1/info"))
                .header("Authorization", "Bearer " + System.getenv("FLOWABLE_POC_TOKEN")).GET().build();
        var response = client.send(request, HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("8.0.0"));
        assertTrue(response.body().contains("4.0.2"));
        assertTrue(response.body().contains("\"poc\":true"));
    }

    @Test void runtime_identity_exposes_stable_process_boot() throws Exception {
        var client = HttpClient.newHttpClient();
        var url = URI.create("http://127.0.0.1:" + port + "/poc/v1/info");
        var req = HttpRequest.newBuilder(url).header("Authorization", "Bearer " + System.getenv("FLOWABLE_POC_TOKEN")).GET().build();
        var json = new com.fasterxml.jackson.databind.ObjectMapper();
        var info = json.readTree(client.send(req, HttpResponse.BodyHandlers.ofString()).body());
        assertTrue(info.hasNonNull("boot_id"));
        assertTrue(java.time.OffsetDateTime.parse(info.get("boot_started_at").asText()).toInstant().toEpochMilli() > 0);
        assertEquals(info.get("boot_id"), json.readTree(client.send(req, HttpResponse.BodyHandlers.ofString()).body()).get("boot_id"));
    }

    @Test void missing_or_short_token_fails_closed() {
        assertThrows(IllegalStateException.class, () -> SecurityConfig.validateToken(null));
        assertThrows(IllegalStateException.class, () -> SecurityConfig.validateToken(""));
        assertThrows(IllegalStateException.class, () -> SecurityConfig.validateToken("x".repeat(31)));
        assertDoesNotThrow(() -> SecurityConfig.validateToken("x".repeat(32)));
    }

    @Test void only_process_engine_and_isolated_database_are_available() {
        assertNotNull(engine.getRuntimeService());
        assertFalse(context.containsBean("cmmnEngine"));
        assertFalse(context.containsBean("dmnEngine"));
        assertTrue(context.getEnvironment().getProperty("spring.datasource.url").contains("flowable_poc"));
        assertTrue(engine.getRepositoryService().createDeploymentQuery().list().stream()
            .allMatch(d -> d.getName().startsWith("poc:")));
    }

    @Test void compose_has_no_pms_mount_or_public_database() throws Exception {
        var yaml = new org.yaml.snakeyaml.Yaml();
        Map<?, ?> doc = yaml.load(Files.readString(Path.of("compose.poc.yml")));
        assertEquals("logix-flowable-poc", doc.get("name"));
        Map<?, ?> services = (Map<?, ?>) doc.get("services");
        assertEquals(java.util.Set.of("poc-db", "runner"), services.keySet());
        assertNull(((Map<?, ?>) services.get("poc-db")).get("ports"));
        assertTrue(((Map<?, ?>) services.get("runner")).get("ports").toString().contains("127.0.0.1:"));
        assertEquals(java.util.Set.of("flowable_poc_pgdata"), ((Map<?, ?>) doc.get("volumes")).keySet());
    }
}
