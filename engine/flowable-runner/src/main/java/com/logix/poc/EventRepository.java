package com.logix.poc;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.*;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Repository
class EventRepository {
    private final JdbcTemplate jdbc;
    private final CommandRepository commands;
    private final ObjectMapper json = new ObjectMapper();
    EventRepository(JdbcTemplate jdbc, CommandRepository commands) { this.jdbc = jdbc; this.commands = commands; }
    void append(Map<String,Object> payload) {
        if (!TransactionSynchronizationManager.isActualTransactionActive()) throw new IllegalStateException("Events require engine transaction");
        commands.lock("poc:journal:commit-order");
        var event = new LinkedHashMap<>(payload);
        UUID id = UUID.randomUUID();
        event.put("event_id", id.toString()); event.put("contract_version", 1);
        event.put("occurred_at", OffsetDateTime.now(ZoneOffset.UTC).toString().replace("Z", "+00:00"));
        jdbc.update("INSERT INTO poc_event(event_id,payload) VALUES (?,?::jsonb)", id, commands.encode(event));
    }
    PocDtos.EventPage after(long cursor, int limit) {
        if (cursor < 0 || limit < 1 || limit > 500) throw new PocException(400, "Invalid event cursor or limit");
        List<Map<String,Object>> rows = jdbc.query("SELECT journal_id,payload::text FROM poc_event WHERE journal_id>? ORDER BY journal_id LIMIT ?", (rs,n) -> {
            try {
                Map<String,Object> data = json.readValue(rs.getString(2), new TypeReference<Map<String,Object>>(){});
                data.put("journal_id", rs.getLong(1)); return data;
            } catch (Exception e) { throw new IllegalStateException("Invalid event", e); }
        }, cursor, limit + 1);
        boolean more = rows.size() > limit;
        var page = more ? new ArrayList<>(rows.subList(0, limit)) : rows;
        long next = page.isEmpty() ? cursor : ((Number) page.getLast().get("journal_id")).longValue();
        return new PocDtos.EventPage(page, next, more);
    }
}
