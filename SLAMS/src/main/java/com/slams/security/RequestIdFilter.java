package com.slams.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

@Component
public class RequestIdFilter extends OncePerRequestFilter {
    public static final String ATTRIBUTE = "slams.requestId";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String supplied = request.getHeader("X-Request-ID");
        String requestId;
        try {
            requestId = supplied == null ? UUID.randomUUID().toString() : UUID.fromString(supplied).toString();
        } catch (IllegalArgumentException ignored) {
            requestId = UUID.randomUUID().toString();
        }
        request.setAttribute(ATTRIBUTE, requestId);
        response.setHeader("X-Request-ID", requestId);
        filterChain.doFilter(request, response);
    }
}
