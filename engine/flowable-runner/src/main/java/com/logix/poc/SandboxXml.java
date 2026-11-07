package com.logix.poc;

import java.util.*;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.*;
import org.xml.sax.InputSource;
import java.io.StringReader;

final class SandboxXml {
    static final String NS = "http://www.omg.org/spec/BPMN/20100524/MODEL";
    static final Map<String,Set<String>> ATTRS = Map.ofEntries(
        Map.entry("definitions", Set.of("id","name","targetNamespace")), Map.entry("process", Set.of("id","name","isExecutable")),
        Map.entry("startEvent", Set.of("id","name")), Map.entry("endEvent", Set.of("id","name")),
        Map.entry("userTask", Set.of("id","name")), Map.entry("parallelGateway", Set.of("id","name","gatewayDirection")),
        Map.entry("sequenceFlow", Set.of("id","name","sourceRef","targetRef")), Map.entry("incoming", Set.of()), Map.entry("outgoing", Set.of()),
        Map.entry("documentation", Set.of()), Map.entry("extensionElements", Set.of()), Map.entry("laneSet", Set.of("id","name")),
        Map.entry("lane", Set.of("id","name")), Map.entry("flowNodeRef", Set.of()));
    static Document check(String xml) {
        if (xml.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 2097152 || xml.contains("<!") || xml.contains("${") || xml.contains("#{")) throw new PocException(400,"Unsupported XML content");
        try {
            var factory = DocumentBuilderFactory.newInstance(); factory.setNamespaceAware(true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl",true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities",false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities",false);
            factory.setAttribute(javax.xml.XMLConstants.ACCESS_EXTERNAL_DTD, ""); factory.setAttribute(javax.xml.XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            var doc = factory.newDocumentBuilder().parse(new InputSource(new StringReader(xml)));
            if (!NS.equals(doc.getDocumentElement().getNamespaceURI()) || !"definitions".equals(doc.getDocumentElement().getLocalName())) throw new PocException(400,"BPMN definitions required");
            var all = doc.getElementsByTagName("*"); var ids = new HashSet<String>();
            var nodes = new LinkedHashMap<String,String>(); var in = new HashMap<String,List<String>>(); var out = new HashMap<String,List<String>>();
            for (int i=0;i<all.getLength();i++) {
                var el=(Element)all.item(i); String tag=el.getLocalName(), ns=el.getNamespaceURI();
                Set<String> allowed;
                if (NS.equals(ns) && ATTRS.containsKey(tag)) allowed=ATTRS.get(tag);
                else if ("http://logix-pms.local/bpmn".equals(ns) && Set.of("nodeType","ownerRole","durationMinutes","waitMinutes","cost","reworkRate","approvalLevels","valueAdded").contains(tag)) allowed=Set.of();
                else if (("http://www.omg.org/spec/BPMN/20100524/DI".equals(ns) && Set.of("BPMNDiagram","BPMNPlane","BPMNShape","BPMNEdge","BPMNLabel").contains(tag)) || ("http://www.omg.org/spec/DD/20100524/DC".equals(ns) && tag.equals("Bounds")) || ("http://www.omg.org/spec/DD/20100524/DI".equals(ns) && tag.equals("waypoint"))) allowed=Set.of("id","bpmnElement","x","y","width","height","isHorizontal","isExpanded","isMarkerVisible");
                else throw new PocException(400,"Unsupported XML element");
                for (int j=0;j<el.getAttributes().getLength();j++) {
                    var a=el.getAttributes().item(j); if (javax.xml.XMLConstants.XMLNS_ATTRIBUTE_NS_URI.equals(a.getNamespaceURI())) continue;
                    if (!allowed.contains(a.getNodeName())) throw new PocException(400,"Unsupported XML attribute");
                }
                if (el.hasAttribute("id") && (!el.getAttribute("id").matches("[A-Za-z_][A-Za-z0-9_.-]{0,127}") || !ids.add(el.getAttribute("id")))) throw new PocException(400,"Invalid XML identity");
                if (NS.equals(ns) && Set.of("startEvent","endEvent","userTask","parallelGateway","sequenceFlow").contains(tag)
                    && (!(el.getParentNode() instanceof Element parent) || !"process".equals(parent.getLocalName()) || !NS.equals(parent.getNamespaceURI()))) throw new PocException(400,"Execution element must be direct process child");
                if (Set.of("startEvent","endEvent","userTask","parallelGateway").contains(tag)) {
                    String id=el.getAttribute("id"); if (id.isEmpty()) throw new PocException(400,"Node ID required");
                    nodes.put(id,tag); in.put(id,new ArrayList<>()); out.put(id,new ArrayList<>());
                }
            }
            var processes=doc.getElementsByTagNameNS(NS,"process");
            if (processes.getLength()!=1 || !"true".equals(((Element)processes.item(0)).getAttribute("isExecutable"))) throw new PocException(400,"One executable process required");
            if (nodes.size()>500) throw new PocException(400,"Too many nodes");
            var flows=doc.getElementsByTagNameNS(NS,"sequenceFlow");
            for(int i=0;i<flows.getLength();i++) { var f=(Element)flows.item(i); String s=f.getAttribute("sourceRef"),t=f.getAttribute("targetRef"); if(!nodes.containsKey(s)||!nodes.containsKey(t)||f.getAttribute("id").isEmpty()) throw new PocException(400,"Invalid flow"); out.get(s).add(t); in.get(t).add(s); }
            var starts=nodes.keySet().stream().filter(k->nodes.get(k).equals("startEvent")).toList(); var ends=nodes.keySet().stream().filter(k->nodes.get(k).equals("endEvent")).toList();
            if(starts.size()!=1||ends.size()!=1) throw new PocException(400,"One start/end required");
            for(String k:nodes.keySet()) { int a=in.get(k).size(),b=out.get(k).size(); boolean ok=switch(nodes.get(k)){case "startEvent"->a==0&&b==1;case "endEvent"->a==1&&b==0;case "userTask"->a==1&&b==1;default->(a==1&&b>=2)||(a>=2&&b==1);}; if(!ok) throw new PocException(400,"Invalid node degree"); }
            var degree=new HashMap<String,Integer>(); in.forEach((k,v)->degree.put(k,v.size())); var queue=new ArrayDeque<>(starts); var order=new ArrayList<String>();
            while(!queue.isEmpty()){String k=queue.remove();order.add(k);for(String t:out.get(k)){degree.put(t,degree.get(t)-1);if(degree.get(t)==0)queue.add(t);}}
            if(order.size()!=nodes.size())throw new PocException(400,"Cycles or unreachable nodes");
            var stacks=new HashMap<String,List<String>>(); var branches=new HashMap<String,List<String>>(); stacks.put(starts.getFirst(),List.of());
            for(String k:order){
                if(in.get(k).size()>1){var incoming=in.get(k).stream().map(s->branches.get(s+"|"+k)).toList(); if(incoming.stream().anyMatch(List::isEmpty))throw new PocException(400,"Unpaired join"); String fork=incoming.getFirst().getLast().split("\\|",2)[0]; var prefix=incoming.getFirst().subList(0,incoming.getFirst().size()-1);var names=new HashSet<String>();
                    for(var s:incoming){if(!s.subList(0,s.size()-1).equals(prefix)||!s.getLast().startsWith(fork+"|"))throw new PocException(400,"Unstructured parallel join");names.add(s.getLast().split("\\|",2)[1]);}
                    if(!names.equals(new HashSet<>(out.get(fork))))throw new PocException(400,"Incomplete join");stacks.put(k,List.copyOf(prefix));
                }else if(!in.get(k).isEmpty())stacks.put(k,branches.get(in.get(k).getFirst()+"|"+k));
                for(String t:out.get(k)){var s=new ArrayList<>(stacks.get(k));if(out.get(k).size()>1)s.add(k+"|"+t);branches.put(k+"|"+t,s);}
            }
            if(!stacks.get(ends.getFirst()).isEmpty())throw new PocException(400,"Unclosed parallel fork");
            return doc;
        } catch(PocException e){throw e;} catch(Exception e){throw new PocException(400,"Invalid sandbox XML");}
    }
}
