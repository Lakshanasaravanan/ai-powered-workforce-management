package com.slams.security;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

@Component
public class DelegationJwtUtil {
    private final ObjectMapper objectMapper;

    @Value("${slams.delegation.enabled:false}")
    private boolean enabled;

    @Value("${slams.delegation.issuer:}")
    private String issuer;

    @Value("${slams.delegation.audience:}")
    private String audience;

    @Value("${slams.delegation.public-key:}")
    private String publicKeyPem;

    public DelegationJwtUtil(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /** An untrusted header check is used only to route RS256 tokens; validation happens below. */
    public boolean isDelegationCandidate(String token) {
        try {
            String[] parts = token.split("\\.");
            if (parts.length != 3) return false;
            JsonNode header = objectMapper.readTree(Base64.getUrlDecoder().decode(parts[0]));
            return "RS256".equals(header.path("alg").asText());
        } catch (Exception ignored) {
            return false;
        }
    }

    public Claims validate(String token) {
        if (!enabled) throw new DelegationAuthenticationException("Delegation authentication is disabled");
        if (issuer.isBlank() || audience.isBlank() || publicKeyPem.isBlank()) {
            throw new DelegationAuthenticationException("Delegation authentication is not configured");
        }
        try {
            Claims claims = Jwts.parserBuilder()
                    .setSigningKey(parsePublicKey())
                    .requireIssuer(issuer)
                    .requireAudience(audience)
                    .build()
                    .parseClaimsJws(token)
                    .getBody();
            String employeeId = claims.get("employee_id", String.class);
            String tokenType = claims.get("token_type", String.class);
            if (employeeId == null || employeeId.isBlank()
                    || !"delegation".equals(tokenType)
                    || claims.getId() == null || claims.getId().isBlank()
                    || !employeeId.equals(claims.getSubject())) {
                throw new DelegationAuthenticationException("Delegation token claims are invalid");
            }
            return claims;
        } catch (DelegationAuthenticationException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new DelegationAuthenticationException("Delegation token is invalid", exception);
        }
    }

    private PublicKey parsePublicKey() throws Exception {
        String normalized = publicKeyPem.replace("\\n", "\n")
                .replace("-----BEGIN PUBLIC KEY-----", "")
                .replace("-----END PUBLIC KEY-----", "")
                .replaceAll("\\s", "");
        byte[] decoded = Base64.getDecoder().decode(normalized.getBytes(StandardCharsets.US_ASCII));
        return KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(decoded));
    }
}
