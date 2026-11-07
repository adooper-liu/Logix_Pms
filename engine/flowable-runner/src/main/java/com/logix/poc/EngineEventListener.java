package com.logix.poc;

import java.util.*;
import org.flowable.common.engine.api.delegate.event.*;
import org.flowable.engine.delegate.event.*;
import org.flowable.engine.impl.persistence.entity.ExecutionEntity;
import org.flowable.task.api.Task;
import org.flowable.job.api.JobInfo;
import org.flowable.spring.SpringProcessEngineConfiguration;
import org.flowable.spring.boot.EngineConfigurationConfigurer;
import org.springframework.context.annotation.*;

@Configuration
class EngineEventListener implements FlowableEventListener {
    private final EventRepository events;
    EngineEventListener(EventRepository events) { this.events = events; }

    @Bean EngineConfigurationConfigurer<SpringProcessEngineConfiguration> journalListener() {
        return config -> config.setEventListeners(List.of(this));
    }
    @Override public Collection<? extends FlowableEventType> getTypes() {
        return List.of(FlowableEngineEventType.PROCESS_STARTED, FlowableEngineEventType.PROCESS_COMPLETED,
            FlowableEngineEventType.PROCESS_CANCELLED, FlowableEngineEventType.TASK_CREATED,
            FlowableEngineEventType.TASK_ASSIGNED, FlowableEngineEventType.TASK_COMPLETED,
            FlowableEngineEventType.ACTIVITY_STARTED, FlowableEngineEventType.ACTIVITY_COMPLETED,
            FlowableEngineEventType.JOB_EXECUTION_SUCCESS, FlowableEngineEventType.JOB_EXECUTION_FAILURE);
    }
    @Override public void onEvent(FlowableEvent event) {
        var row = new LinkedHashMap<String,Object>(); row.put("type", event.getType().name());
        if (event instanceof FlowableEngineEvent e) {
            row.put("engine_instance_id", e.getProcessInstanceId()); row.put("definition_id", e.getProcessDefinitionId());
            row.put("execution_id", e.getExecutionId());
        }
        if (event instanceof FlowableActivityEvent a) row.put("activity_id", a.getActivityId());
        if (event instanceof FlowableEntityEvent e) {
            if (e.getEntity() instanceof Task t) {
                row.put("task_id", t.getId()); row.put("activity_id", t.getTaskDefinitionKey());
            }
            if (e.getEntity() instanceof JobInfo j) row.put("job_id", j.getId());
            if (e.getEntity() instanceof ExecutionEntity x) {
                row.put("business_key", x.getBusinessKey()); row.put("context", x.getVariable("pocContext"));
            }
        }
        // The active command context still contains the root execution, including at completion.
        if (row.get("engine_instance_id") != null) {
            var ctx = org.flowable.common.engine.impl.context.Context.getCommandContext();
            if (ctx != null) {
                var config = org.flowable.engine.impl.util.CommandContextUtil.getProcessEngineConfiguration(ctx);
                var root = config.getExecutionEntityManager().findById(row.get("engine_instance_id").toString());
                if (root != null) { row.put("business_key", root.getBusinessKey()); row.put("context", root.getVariable("sandboxContext") != null ? root.getVariable("sandboxContext") : root.getVariable("pocContext")); }
            }
        }
        events.append(row);
    }
    @Override public boolean isFailOnException() { return true; }
    @Override public boolean isFireOnTransactionLifecycleEvent() { return false; }
    @Override public String getOnTransaction() { return null; }
}
