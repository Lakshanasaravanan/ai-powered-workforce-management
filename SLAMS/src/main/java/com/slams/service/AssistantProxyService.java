package com.slams.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.time.Duration;
import java.util.Date;
import java.util.Map;

@Service
public class AssistantProxyService {
    private final ObjectMapper json;
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
    @Value("${assistant.proxy.base-url}") private String baseUrl;
    @Value("${assistant.proxy.jwt-secret}") private String secret;
    @Value("${assistant.proxy.issuer}") private String issuer;
    @Value("${assistant.proxy.audience}") private String audience;
    public AssistantProxyService(ObjectMapper json) { this.json = json; }
    private String token(String employeeId, String name) {
        Key key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8)); long now = System.currentTimeMillis();
        return Jwts.builder().setIssuer(issuer).setAudience(audience).setSubject(employeeId).claim("employee_id", employeeId).claim("name", name).claim("token_type", "assistant").setIssuedAt(new Date(now)).setExpiration(new Date(now + 120_000)).signWith(key, SignatureAlgorithm.HS256).compact();
    }
    public JsonNode forward(String path, String employeeId, String name, Map<String, Object> body) {
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(baseUrl + path)).timeout(Duration.ofSeconds(8)).header("Authorization", "Bearer " + token(employeeId, name)).header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() == 401 || response.statusCode() == 403 || response.statusCode() == 429 || response.statusCode() >= 500) throw new AssistantProxyException(response.statusCode());
            if (response.statusCode() >= 400) throw new AssistantProxyException(400);
            return json.readTree(response.body());
        } catch (AssistantProxyException exception) { throw exception; }
        catch (Exception exception) { throw new AssistantProxyException(503); }
    }
    public static class AssistantProxyException extends RuntimeException { private final int status; AssistantProxyException(int status) { this.status=status; } public int status() { return status; } }
}
