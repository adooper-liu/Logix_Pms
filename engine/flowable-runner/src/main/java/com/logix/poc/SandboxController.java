package com.logix.poc;

import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/sandbox/v1")
class SandboxController {
    final SandboxService sandbox;
    final CommandService commands;
    final CommandRepository receipts;
    final EventRepository events;
    final PocController poc;
    SandboxController(SandboxService sandbox,CommandService commands,CommandRepository receipts,EventRepository events,PocController poc){this.sandbox=sandbox;this.commands=commands;this.receipts=receipts;this.events=events;this.poc=poc;}
    @GetMapping("/info") Object info(){var result=new LinkedHashMap<>(poc.info());result.put("sandbox",true);result.put("namespace",sandbox.namespace);result.put("contract_version",1);return result;}
    @PostMapping("/commands") Object command(@RequestBody PocDtos.CommandRequest request){if(request.action()==null||!request.action().startsWith("SB_"))throw new PocException(400,"Sandbox action required");return commands.execute(request);}
    @GetMapping("/commands/{id}") Object receipt(@PathVariable UUID id){var r=receipts.find(id).orElseThrow(()->new PocException(404,"Command not committed"));if(!r.action().startsWith("SB_"))throw new PocException(404,"Command outside sandbox");return r;}
    @GetMapping("/instances/{id}") Object instance(@PathVariable String id){return sandbox.instance(id);}
    @GetMapping("/events") Object events(@RequestParam(defaultValue="0") long after_id,@RequestParam(defaultValue="100") int limit){return events.after(after_id,limit);}
}
