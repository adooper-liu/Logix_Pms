package com.logix.poc;

import java.util.*;
import org.flowable.engine.ProcessEngine;
import org.flowable.engine.ProcessEngineConfiguration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringBootVersion;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/poc/v1")
class PocController {
    private final ProcessEngine engine;
    private final JdbcTemplate jdbc;
    private final String revision;
    private final String bootId = UUID.randomUUID().toString();
    private final String bootStartedAt = utc(new Date(java.lang.management.ManagementFactory.getRuntimeMXBean().getStartTime()));

    private static String utc(Date date) {
        return date == null ? null : date.toInstant().toString().replace("Z", "+00:00");
    }

    private final FixtureService fixtures;
    private final CommandService commands;
    private final CommandRepository receipts;
    private final EventRepository events;
    PocController(ProcessEngine engine, JdbcTemplate jdbc, @Value("${poc.build-revision}") String revision,
            FixtureService fixtures, CommandService commands, CommandRepository receipts, EventRepository events) {
        this.engine = engine; this.jdbc = jdbc; this.revision = revision;
        this.fixtures = fixtures; this.commands = commands; this.receipts = receipts; this.events = events;
    }
    @GetMapping("/fixtures") Object fixtures() { return fixtures.list(); }
    @PostMapping("/commands") Object command(@RequestBody PocDtos.CommandRequest request) { return commands.execute(request); }
    @GetMapping("/commands/{id}") Object receipt(@PathVariable UUID id) { return receipts.find(id).orElseThrow(() -> new PocException(404, "Command not committed")); }
    @GetMapping("/events") Object events(@RequestParam(defaultValue="0") long after_id, @RequestParam(defaultValue="100") int limit) { return events.after(after_id, limit); }
    @GetMapping("/instances/{id}") Map<String,Object> instance(@PathVariable String id) {
        var historic = engine.getHistoryService().createHistoricProcessInstanceQuery().processInstanceId(id).singleResult();
        if (historic == null) throw new PocException(404, "POC instance not found");
        fixtures.fixtureForDefinition(historic.getProcessDefinitionId());
        var active = engine.getRuntimeService().createProcessInstanceQuery().processInstanceId(id).singleResult();
        var out = new LinkedHashMap<String,Object>();
        out.put("instance_id", id); out.put("definition_id", historic.getProcessDefinitionId()); out.put("business_key", historic.getBusinessKey());
        out.put("status", active != null ? (active.isSuspended() ? "SUSPENDED" : "RUNNING") : historic.getDeleteReason() == null ? "COMPLETED" : "CANCELLED");
        out.put("tasks", engine.getTaskService().createTaskQuery().processInstanceId(id).list().stream().map(t -> {
            var task = new LinkedHashMap<String,Object>(); task.put("task_id", t.getId()); task.put("activity_id", t.getTaskDefinitionKey());
            task.put("execution_id", t.getExecutionId()); task.put("assignee", t.getAssignee());
            task.put("candidates", engine.getTaskService().getIdentityLinksForTask(t.getId()).stream().filter(l -> "candidate".equals(l.getType())).map(l -> l.getUserId()).filter(Objects::nonNull).toList());
            return task;
        }).toList());
        out.put("subscriptions", engine.getRuntimeService().createEventSubscriptionQuery().processInstanceId(id).list().stream()
            .map(s -> Map.of("name", s.getEventName(), "execution_id", s.getExecutionId())).toList());
        var timers = engine.getManagementService().createTimerJobQuery().processInstanceId(id).list();
        out.put("timer_jobs", timers.size());
        out.put("timer_due_at", timers.size() == 1 ? utc(timers.getFirst().getDuedate()) : null);
        out.put("completed_at", utc(historic.getEndTime()));
        out.put("deadletter_jobs", engine.getManagementService().createDeadLetterJobQuery().processInstanceId(id).count());
        var outcome = engine.getHistoryService().createHistoricVariableInstanceQuery().processInstanceId(id).variableName("outcome").singleResult();
        out.put("outcome", outcome == null ? null : outcome.getValue());
        return out;
    }
    @GetMapping("/health") Map<String,Object> health() {
        jdbc.queryForObject("SELECT 1", Integer.class);
        engine.getRepositoryService().createDeploymentQuery().count();
        return Map.of("status", "ready", "poc", true);
    }
    @GetMapping("/info") Map<String,Object> info() {
        return Map.of("poc", true, "build_revision", revision, "boot_id", bootId, "boot_started_at", bootStartedAt, "flowable_version", ProcessEngine.VERSION,
            "spring_boot_version", SpringBootVersion.getVersion(), "java_version", System.getProperty("java.version"),
            "capability_names", List.of("serial", "parallel_join", "all_reviewers", "message_timer", "suspend_resume_cancel", "command_replay", "transactional_event_journal"));
    }
}
