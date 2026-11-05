package com.logix.poc;

import java.security.MessageDigest;
import java.util.*;
import org.flowable.engine.ProcessEngine;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

@Service
class FixtureService {
    private static final List<String> NAMES = List.of("serial", "parallel-signoff", "message-timer");
    private final ProcessEngine engine;
    private final CommandRepository commands;
    FixtureService(ProcessEngine engine, CommandRepository commands) { this.engine = engine; this.commands = commands; }
    private byte[] bytes(String name) {
        if (!NAMES.contains(name)) throw new PocException(400, "Unknown fixed fixture");
        try { return new ClassPathResource("fixtures/" + name + ".bpmn20.xml").getInputStream().readAllBytes(); }
        catch (Exception e) { throw new IllegalStateException("Fixture unavailable", e); }
    }
    String hash(String name) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes(name))); }
        catch (PocException e) { throw e; } catch (Exception e) { throw new IllegalStateException(e); }
    }
    List<Map<String,Object>> list() { return NAMES.stream().map(n -> Map.<String,Object>of("name", n, "bpmn_sha256", hash(n))).toList(); }
    PocDtos.DeploymentResult deploy(String fixture, String expected) {
        String sha = hash(fixture);
        if (!sha.equals(expected)) throw new PocException(400, "Fixture hash mismatch");
        commands.lock("poc:fixture:" + fixture);
        var repo = engine.getRepositoryService(); String name = "poc:" + fixture + ":" + sha;
        var deployment = repo.createDeploymentQuery().deploymentName(name).singleResult();
        if (deployment == null) deployment = repo.createDeployment().name(name).addBytes(fixture + ".bpmn20.xml", bytes(fixture)).deploy();
        var definition = repo.createProcessDefinitionQuery().deploymentId(deployment.getId()).singleResult();
        return new PocDtos.DeploymentResult(deployment.getId(), definition.getId(), definition.getKey(), definition.getVersion(), sha);
    }
    String fixtureForDefinition(String id) {
        var definition = engine.getRepositoryService().createProcessDefinitionQuery().processDefinitionId(id).singleResult();
        if (definition == null) throw new PocException(400, "Unknown POC definition");
        var deployment = engine.getRepositoryService().createDeploymentQuery().deploymentId(definition.getDeploymentId()).singleResult();
        for (String name : NAMES) if (deployment.getName().equals("poc:" + name + ":" + hash(name))) return name;
        throw new PocException(400, "Definition is not a fixed POC fixture");
    }
}
