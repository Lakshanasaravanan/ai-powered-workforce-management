package com.slams.controller;
import com.fasterxml.jackson.databind.JsonNode;
import com.slams.model.Role;
import com.slams.model.User;
import com.slams.service.AssistantProxyService;
import com.slams.service.UserService;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import java.security.Principal;
import java.util.Map;
import java.util.HashMap;

@RestController @RequestMapping("/api/assistant")
@PreAuthorize("hasRole('EMPLOYEE')")
public class AssistantProxyController {
  private final AssistantProxyService proxy; private final UserService users;
  public AssistantProxyController(AssistantProxyService proxy, UserService users) { this.proxy=proxy; this.users=users; }
  private User employee(Principal p) { return users.findByUsername(p.getName()).filter(u -> u.getRole()== Role.ROLE_EMPLOYEE).orElseThrow(); }
  @PostMapping("/chat") public ResponseEntity<?> chat(@RequestBody Map<String,Object> body, Principal p) { try { User u=employee(p); return ResponseEntity.ok(proxy.forward("/api/v1/chat",u.getEmployeeId(),u.getFullName(), chatBody(body))); } catch(AssistantProxyService.AssistantProxyException e) { return safe(e); } }
  @PostMapping("/confirm") public ResponseEntity<?> confirm(@RequestBody Map<String,Object> body, Principal p) { try { User u=employee(p); return ResponseEntity.ok(proxy.forward("/api/v1/chat/confirm",u.getEmployeeId(),u.getFullName(), Map.of("action_id",body.get("action_id"),"conversation_id",body.get("conversation_id")))); } catch(AssistantProxyService.AssistantProxyException e) { return safe(e); } }
  private Map<String,Object> chatBody(Map<String,Object> body) { Map<String,Object> safe=new HashMap<>(); safe.put("message",body.get("message")); if(body.get("conversation_id")!=null) safe.put("conversation_id",body.get("conversation_id")); return safe; }
  private ResponseEntity<Map<String,String>> safe(AssistantProxyService.AssistantProxyException e) { int status = e.status(); int code = status == 429 ? 429 : (status == 401 || status == 403 ? status : 503); String message = code == 429 ? "Assistant rate limit reached. Please try again shortly." : (code == 401 ? "Please sign in again." : code == 403 ? "You are not permitted to use the assistant." : "Assistant is temporarily unavailable. Please try again."); return ResponseEntity.status(code).body(Map.of("message", message)); }
}
