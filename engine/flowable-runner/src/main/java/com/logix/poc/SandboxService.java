package com.logix.poc;

import java.util.*;
import org.flowable.engine.ProcessEngine;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import com.fasterxml.jackson.databind.ObjectMapper;

@Service
class SandboxService {
    private final ProcessEngine engine;
    private final CommandRepository records;
    final String namespace;
    private final ObjectMapper json = new ObjectMapper();
    SandboxService(ProcessEngine engine, CommandRepository records, @Value("${sandbox.namespace:logix-r3-sandbox}") String namespace) {
        this.engine=engine; this.records=records; this.namespace=namespace;
        if(!namespace.matches("[A-Za-z0-9_-]{1,64}"))throw new IllegalStateException("Invalid sandbox namespace");
    }
    String hash(String value) {
        try{return java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)));}
        catch(Exception e){throw new IllegalStateException(e);}
    }
    @SuppressWarnings("unchecked")
    Map<String,Object> config(String definition) {
        var def=engine.getRepositoryService().createProcessDefinitionQuery().processDefinitionId(definition).singleResult();
        if(def==null)throw new PocException(404,"Definition not found");
        var deploy=engine.getRepositoryService().createDeploymentQuery().deploymentId(def.getDeploymentId()).singleResult();
        if(!deploy.getName().startsWith("sandbox:"+namespace+":"))throw new PocException(403,"Definition outside namespace");
        try(var stream=engine.getRepositoryService().getResourceAsStream(deploy.getId(),"sandbox-config.json")) {return json.readValue(stream,Map.class);}
        catch(Exception e){throw new PocException(503,"Definition configuration unavailable");}
    }
    void contextMatches(Map<String,Object> context, Map<String,Object> config) {
        if(!Objects.equals(context.get("process_id"), config.get("process_id")) || !Objects.equals(context.get("model_version_id"), config.get("model_version_id")))throw new PocException(409,"Model context mismatch");
    }
    @SuppressWarnings("unchecked")
    Map<String,Object> perform(PocDtos.CommandRequest r) {
        if(r.action().equals("SB_DEPLOY"))return deploy(r);
        if(r.action().equals("SB_START")) {
            CommandService.fields(r.payload(),Set.of("business_key","context"));
            var config=config(r.target()); var context=(Map<String,Object>)r.payload().get("context");
            if(context==null || !(context.get("instance_id") instanceof Number))throw new PocException(400,"Local instance context required");
            contextMatches(context,config);
            String business=CommandService.text(r.payload(),"business_key");
            if(!business.matches("sandbox:[A-Za-z0-9:-]{1,120}"))throw new PocException(400,"Sandbox business identity required");
            records.lock("sandbox:"+namespace+":business:"+business);
            if(engine.getHistoryService().createHistoricProcessInstanceQuery().processInstanceBusinessKey(business).count()!=0)throw new PocException(409,"Business already started");
            var stored=new HashMap<>(context);stored.put("namespace",namespace);
            var instance=engine.getRuntimeService().startProcessInstanceById(r.target(),business,Map.of("sandboxContext",stored));
            return Map.of("instance_id",instance.getId(),"definition_id",r.target(),"business_key",business);
        }
        if(Set.of("SB_CLAIM","SB_COMPLETE","SB_ASSIGN").contains(r.action())) {
            CommandService.fields(r.payload(),r.action().equals("SB_ASSIGN")?Set.of("actor","assignee"):r.action().equals("SB_COMPLETE")?Set.of("actor","form_hash","completion"):Set.of("actor"));
            String actor=CommandService.text(r.payload(),"actor");
            if(!actor.matches("pms:[1-9][0-9]*"))throw new PocException(403,"PMS actor required");
            records.lock("sandbox:"+namespace+":task:"+r.target());
            var task=engine.getTaskService().createTaskQuery().taskId(r.target()).singleResult();
            if(task==null)throw new PocException(409,"Task not active");config(task.getProcessDefinitionId());
            var instance=engine.getRuntimeService().createProcessInstanceQuery().processInstanceId(task.getProcessInstanceId()).singleResult();
            if(instance==null||instance.isSuspended())throw new PocException(409,"Instance not active");
            var candidates=engine.getTaskService().getIdentityLinksForTask(task.getId()).stream().filter(l->"candidate".equals(l.getType())).map(l->l.getUserId()).toList();
            if(r.action().equals("SB_ASSIGN")) {
                String assignee=CommandService.text(r.payload(),"assignee");
                if(!candidates.contains(assignee))throw new PocException(403,"Assignment outside frozen candidates");
                engine.getTaskService().setAssignee(task.getId(),assignee);
            } else {
                if(task.getAssignee()!=null?!actor.equals(task.getAssignee()):!candidates.contains(actor))throw new PocException(403,"Actor not assigned or candidate");
                if(r.action().equals("SB_CLAIM"))engine.getTaskService().claim(task.getId(),actor);
                else {
                    if (task.getAssignee() == null) engine.getTaskService().claim(task.getId(), actor);
                    engine.getTaskService().complete(task.getId());
                }
            }
            return Map.of("instance_id",task.getProcessInstanceId(),"task_id",task.getId());
        }
        CommandService.fields(r.payload(),Set.of());
        records.lock("sandbox:"+namespace+":instance:"+r.target());
        var instance=engine.getRuntimeService().createProcessInstanceQuery().processInstanceId(r.target()).singleResult();
        if(instance==null)throw new PocException(409,"Instance not active");config(instance.getProcessDefinitionId());
        switch(r.action()) {
            case "SB_SUSPEND" -> {if(instance.isSuspended())throw new PocException(409,"Already suspended");engine.getRuntimeService().suspendProcessInstanceById(r.target());}
            case "SB_RESUME" -> {if(!instance.isSuspended())throw new PocException(409,"Not suspended");engine.getRuntimeService().activateProcessInstanceById(r.target());}
            case "SB_CANCEL" -> engine.getRuntimeService().deleteProcessInstance(r.target(),"Sandbox controlled cancellation");
            default -> throw new PocException(400,"Unsupported sandbox action");
        }
        return Map.of("instance_id",r.target());
    }
    @SuppressWarnings("unchecked")
    Map<String,Object> deploy(PocDtos.CommandRequest r) {
        CommandService.fields(r.payload(),Set.of("xml","xml_hash","basis_hash","process_id","model_version_id","assignments"));
        Object raw=r.payload().get("xml");if(!(raw instanceof String xml))throw new PocException(400,"XML required");
        var doc=SandboxXml.check(xml);String sourceHash=hash(xml);
        if(!sourceHash.equals(r.payload().get("xml_hash")))throw new PocException(400,"XML hash mismatch");
        if(!(r.payload().get("assignments") instanceof Map<?,?> assignments))throw new PocException(400,"Assignments required");
        var tasks=doc.getElementsByTagNameNS(SandboxXml.NS,"userTask");var names=new HashSet<String>();
        for(int i=0;i<tasks.getLength();i++) {
            var el=(org.w3c.dom.Element)tasks.item(i);String id=el.getAttribute("id");names.add(id);
            if(!(assignments.get(id) instanceof List<?> people)||people.isEmpty()||people.stream().anyMatch(p->!(p instanceof String s)||!s.matches("pms:[1-9][0-9]*")))throw new PocException(400,"Explicit candidate identities required");
            el.setAttributeNS("http://flowable.org/bpmn","flowable:candidateUsers",String.join(",",(List<String>)people));
        }
        if(!names.equals(assignments.keySet()))throw new PocException(400,"Unknown assignment activity");
        try {
            var transformer=javax.xml.transform.TransformerFactory.newInstance().newTransformer();var output=new java.io.StringWriter();
            transformer.transform(new javax.xml.transform.dom.DOMSource(doc),new javax.xml.transform.stream.StreamResult(output));
            String executable=output.toString();String basis=CommandService.text(r.payload(),"basis_hash");
            String name="sandbox:"+namespace+":"+r.target()+":"+sourceHash+":"+basis;
            records.lock(name);
            var deployment=engine.getRepositoryService().createDeploymentQuery().deploymentName(name).singleResult();
            if(deployment==null)deployment=engine.getRepositoryService().createDeployment().name(name).addString("sandbox.bpmn20.xml",executable)
                .addString("sandbox-config.json",json.writeValueAsString(r.payload())).deploy();
            var def=engine.getRepositoryService().createProcessDefinitionQuery().deploymentId(deployment.getId()).singleResult();
            return Map.of("definition_id",def.getId(),"deployment_id",deployment.getId(),"xml_hash",sourceHash,"execution_hash",hash(executable),"namespace",namespace);
        } catch(PocException e){throw e;} catch(Exception e){throw new PocException(400,"Sandbox deployment rejected");}
    }
    static String utc(Date date){return date==null?null:date.toInstant().toString().replace("Z","+00:00");}
    Map<String,Object> instance(String id) {
        var h=engine.getHistoryService().createHistoricProcessInstanceQuery().processInstanceId(id).singleResult();if(h==null)throw new PocException(404,"Instance not found");config(h.getProcessDefinitionId());
        var active=engine.getRuntimeService().createProcessInstanceQuery().processInstanceId(id).singleResult();
        var view=new LinkedHashMap<String,Object>();view.put("instance_id",id);view.put("definition_id",h.getProcessDefinitionId());view.put("business_key",h.getBusinessKey());
        view.put("status",active!=null?(active.isSuspended()?"SUSPENDED":"RUNNING"):h.getDeleteReason()==null?"COMPLETED":"CANCELLED");view.put("started_at",utc(h.getStartTime()));view.put("completed_at",utc(h.getEndTime()));
        var ctx=engine.getHistoryService().createHistoricVariableInstanceQuery().processInstanceId(id).variableName("sandboxContext").singleResult();view.put("context",ctx==null?null:ctx.getValue());
        view.put("tasks",engine.getTaskService().createTaskQuery().processInstanceId(id).list().stream().map(t->{var m=new LinkedHashMap<String,Object>();m.put("task_id",t.getId());m.put("activity_id",t.getTaskDefinitionKey());m.put("execution_id",t.getExecutionId());m.put("name",t.getName());m.put("assignee",t.getAssignee());m.put("created_at",utc(t.getCreateTime()));m.put("candidates",engine.getTaskService().getIdentityLinksForTask(t.getId()).stream().filter(l->"candidate".equals(l.getType())).map(l->l.getUserId()).filter(Objects::nonNull).toList());return m;}).toList());
        view.put("history_tasks",engine.getHistoryService().createHistoricTaskInstanceQuery().processInstanceId(id).list().stream().map(t->{var m=new LinkedHashMap<String,Object>();m.put("task_id",t.getId());m.put("activity_id",t.getTaskDefinitionKey());m.put("execution_id",t.getExecutionId());m.put("name",t.getName());m.put("assignee",t.getAssignee());m.put("created_at",utc(t.getCreateTime()));m.put("completed_at",utc(t.getEndTime()));m.put("delete_reason",t.getDeleteReason());return m;}).toList());
        return view;
    }
}
