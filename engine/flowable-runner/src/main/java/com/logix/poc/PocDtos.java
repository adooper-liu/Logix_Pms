package com.logix.poc;

import java.util.*;

final class PocDtos {
    record CommandRequest(UUID command_id, String action, String target, Map<String,Object> payload) {}
    record CommandReceipt(UUID command_id, String action, Map<String,Object> result) {}
    record EventPage(List<Map<String,Object>> events, long next_after_id, boolean has_more) {}
    record DeploymentResult(String deployment_id, String definition_id, String definition_key, int definition_version, String bpmn_sha256) {
        Map<String,Object> asMap() { return Map.of("deployment_id", deployment_id, "definition_id", definition_id,
            "definition_key", definition_key, "definition_version", definition_version, "bpmn_sha256", bpmn_sha256); }
    }
}
