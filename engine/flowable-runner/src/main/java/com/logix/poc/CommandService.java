package com.logix.poc;

import java.util.*;
import org.flowable.engine.ProcessEngine;
import org.flowable.task.api.Task;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
class CommandService {
    private final CommandRepository records;
    private final FixtureService fixtures;
    private final ProcessEngine engine;
    private final TransactionTemplate transaction;
    CommandService(CommandRepository records, FixtureService fixtures, ProcessEngine engine, PlatformTransactionManager tx) {
        this.records = records; this.fixtures = fixtures; this.engine = engine; this.transaction = new TransactionTemplate(tx);
    }
    PocDtos.CommandReceipt execute(PocDtos.CommandRequest request) {
        if (request.command_id() == null || request.action() == null || request.target() == null || request.payload() == null)
            throw new PocException(400, "Command identity, action, target and payload required");
        String hash = records.hash(request);
        try {
            return transaction.execute(s -> {
                records.begin(request.command_id(), hash);
                var result = perform(request);
                var receipt = new PocDtos.CommandReceipt(request.command_id(), request.action(), result);
                records.finish(receipt); return receipt;
            });
        } catch (DuplicateKeyException ex) {
            var existing = records.find(request.command_id());
            if (existing.isEmpty()) throw ex;
            if (!hash.equals(records.existingHash(request.command_id()))) throw new PocException(409, "Command identity already used with different content");
            return existing.get();
        }
    }
    private Map<String,Object> perform(PocDtos.CommandRequest r) {
        return switch (r.action()) {
            case "DEPLOY" -> { fields(r.payload(), Set.of("bpmn_sha256")); yield fixtures.deploy(r.target(), text(r.payload(), "bpmn_sha256")).asMap(); }
            case "START" -> start(r);
            case "CLAIM", "COMPLETE" -> task(r);
            case "MESSAGE", "SUSPEND", "RESUME", "CANCEL" -> control(r);
            default -> throw new PocException(400, "Unsupported POC action");
        };
    }
    static void fields(Map<String,Object> map, Set<String> allowed) {
        if (!allowed.containsAll(map.keySet())) throw new PocException(400, "Unknown payload fields");
    }
    static String text(Map<String,Object> map, String key) {
        if (!(map.get(key) instanceof String s) || s.isBlank() || s.length() > 256) throw new PocException(400, "Missing or invalid " + key);
        return s;
    }
    @SuppressWarnings("unchecked")
    private Map<String,Object> start(PocDtos.CommandRequest r) {
        fields(r.payload(), Set.of("business_key", "context", "variables"));
        String fixture = fixtures.fixtureForDefinition(r.target());
        String business = text(r.payload(), "business_key");
        if (!business.matches("poc:[0-9a-fA-F-]{36}:[a-zA-Z0-9_-]{1,64}")) throw new PocException(400, "Synthetic business key required");
        if (!(r.payload().get("context") instanceof Map<?,?> raw)) throw new PocException(400, "Synthetic context required");
        var context = (Map<String,Object>) raw;
        fields(context, Set.of("source", "process_id", "model_version_id", "project_id", "round_id"));
        if (!"POC_FIXTURE".equals(context.get("source")) || !Objects.equals(context.get("process_id"), 910001)
                || !Objects.equals(context.get("model_version_id"), 910001) || context.get("project_id") != null || context.get("round_id") != null)
            throw new PocException(400, "Only fixed synthetic context allowed");
        if (!(r.payload().get("variables") instanceof Map<?,?> v)) throw new PocException(400, "Fixture variables required");
        var vars = new HashMap<String,Object>();
        if (fixture.equals("message-timer")) {
            if (!Set.of("waitDuration").containsAll(v.keySet())) throw new PocException(400, "Unknown fixture variables");
            String duration = Objects.toString(v.getOrDefault("waitDuration", null), "PT5S");
            try {
                var time = java.time.Duration.parse(duration);
                if (time.compareTo(java.time.Duration.ofSeconds(2)) < 0 || time.compareTo(java.time.Duration.ofSeconds(60)) > 0) throw new IllegalArgumentException();
            } catch (Exception ex) { throw new PocException(400, "waitDuration must be ISO duration between 2 and 60 seconds"); }
            vars.put("waitDuration", duration);
        } else if (!v.isEmpty()) throw new PocException(400, "Unknown fixture variables");
        if (fixture.equals("parallel-signoff")) vars.put("reviewers", List.of("poc-reviewer-a", "poc-reviewer-b"));
        records.lock("poc:business:" + business);
        if (engine.getHistoryService().createHistoricProcessInstanceQuery().processInstanceBusinessKey(business).count() != 0)
            throw new PocException(409, "Business key already started; query original command");
        vars.put("pocContext", context);
        var instance = engine.getRuntimeService().startProcessInstanceById(r.target(), business, vars);
        return Map.of("instance_id", instance.getId(), "definition_id", r.target(), "business_key", business);
    }
    private Map<String,Object> control(PocDtos.CommandRequest r) {
        records.lock("poc:instance:" + r.target());
        var runtime = engine.getRuntimeService();
        var instance = runtime.createProcessInstanceQuery().processInstanceId(r.target()).singleResult();
        if (instance == null) throw new PocException(409, "Instance not active");
        fixtures.fixtureForDefinition(instance.getProcessDefinitionId());
        if (r.action().equals("MESSAGE")) {
            fields(r.payload(), Set.of("message_name"));
            if (!"PocResponse".equals(text(r.payload(), "message_name"))) throw new PocException(400, "Unknown fixture message");
            if (instance.isSuspended()) throw new PocException(409, "Instance suspended");
            var subs = runtime.createEventSubscriptionQuery().processInstanceId(instance.getId()).eventName("PocResponse").list();
            if (subs.size() != 1) throw new PocException(409, "Exactly one message subscription required");
            runtime.messageEventReceived("PocResponse", subs.getFirst().getExecutionId());
        } else {
            fields(r.payload(), Set.of());
            switch (r.action()) {
                case "SUSPEND" -> { if (instance.isSuspended()) throw new PocException(409, "Already suspended"); runtime.suspendProcessInstanceById(instance.getId()); }
                case "RESUME" -> { if (!instance.isSuspended()) throw new PocException(409, "Not suspended"); runtime.activateProcessInstanceById(instance.getId()); }
                case "CANCEL" -> runtime.deleteProcessInstance(instance.getId(), "POC synthetic cancellation; no business compensation");
                default -> throw new PocException(400, "Unsupported control");
            }
        }
        return Map.of("instance_id", r.target(), "action", r.action());
    }
    private Map<String,Object> task(PocDtos.CommandRequest r) {
        fields(r.payload(), Set.of("actor"));
        String actor = text(r.payload(), "actor");
        if (!Set.of("poc-applicant", "poc-quality", "poc-plan", "poc-reviewer-a", "poc-reviewer-b").contains(actor)) throw new PocException(403, "Unknown synthetic actor");
        records.lock("poc:task:" + r.target());
        Task task = engine.getTaskService().createTaskQuery().taskId(r.target()).singleResult();
        if (task == null) throw new PocException(409, "Task not active");
        var instance = engine.getRuntimeService().createProcessInstanceQuery().processInstanceId(task.getProcessInstanceId()).singleResult();
        if (instance == null || instance.isSuspended()) throw new PocException(409, "Instance not active");
        boolean candidate = engine.getTaskService().getIdentityLinksForTask(task.getId()).stream()
            .anyMatch(l -> "candidate".equals(l.getType()) && actor.equals(l.getUserId()));
        if ((task.getAssignee() != null && !actor.equals(task.getAssignee())) || (task.getAssignee() == null && !candidate)) throw new PocException(403, "Actor not assigned or candidate");
        if (r.action().equals("CLAIM")) engine.getTaskService().claim(task.getId(), actor);
        else engine.getTaskService().complete(task.getId());
        return Map.of("task_id", task.getId(), "instance_id", task.getProcessInstanceId(), "action", r.action());
    }
}
