package com.logix.poc;

import java.util.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class CommandRepository {
    private final JdbcTemplate jdbc;
    private final ObjectMapper json = new ObjectMapper();
    CommandRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    String encode(Object value) {
        try { return json.writeValueAsString(value); } catch (Exception e) { throw new IllegalStateException("Cannot encode journal", e); }
    }
    String hash(PocDtos.CommandRequest req) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(encode(canonical(Map.of(
                "action", req.action(), "target", req.target(), "payload", req.payload()))).getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) { throw new PocException(400, "Invalid command"); }
    }
    private Object canonical(Object x) {
        if (x instanceof Map<?,?> m) {
            var sorted = new TreeMap<String,Object>(); m.forEach((k,v) -> sorted.put(k.toString(), canonical(v))); return sorted;
        }
        if (x instanceof List<?> l) return l.stream().map(this::canonical).toList();
        return x;
    }
    Optional<PocDtos.CommandReceipt> find(UUID id) {
        return jdbc.query("SELECT receipt::text FROM poc_command WHERE command_id=? AND receipt IS NOT NULL", (rs,n) -> {
            try { return json.readValue(rs.getString(1), PocDtos.CommandReceipt.class); }
            catch (Exception e) { throw new IllegalStateException("Invalid receipt", e); }
        }, id).stream().findFirst();
    }
    String existingHash(UUID id) { return jdbc.queryForObject("SELECT request_hash FROM poc_command WHERE command_id=?", String.class, id); }
    void begin(UUID id, String hash) { jdbc.update("INSERT INTO poc_command(command_id,request_hash) VALUES (?,?)", id, hash); }
    void finish(PocDtos.CommandReceipt r) { jdbc.update("UPDATE poc_command SET receipt=?::jsonb WHERE command_id=?", encode(r), r.command_id()); }
    void lock(String scope) { jdbc.queryForList("SELECT pg_advisory_xact_lock(hashtextextended(?,0))", scope); }
}
