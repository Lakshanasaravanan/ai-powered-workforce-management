package com.slams.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.slams.dto.ApiErrorResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.time.Instant;
import java.util.UUID;

@Component
public class ApiErrorWriter {
    private final ObjectMapper objectMapper;

    public ApiErrorWriter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public void write(HttpServletRequest request, HttpServletResponse response, HttpStatus status, String code, String message)
            throws IOException {
        String requestId = (String) request.getAttribute(RequestIdFilter.ATTRIBUTE);
        if (requestId == null) {
            requestId = UUID.randomUUID().toString();
            response.setHeader("X-Request-ID", requestId);
        }
        response.setStatus(status.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        objectMapper.writeValue(response.getOutputStream(), new ApiErrorResponse(code, message, requestId, Instant.now()));
    }
}
