package com.slams.security;

import com.slams.model.User;
import com.slams.service.UserService;
import io.jsonwebtoken.Claims;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
public class DelegationAuthenticationFilter extends OncePerRequestFilter {
    private final DelegationJwtUtil delegationJwtUtil;
    private final UserService userService;
    private final ApiErrorWriter errorWriter;

    public DelegationAuthenticationFilter(DelegationJwtUtil delegationJwtUtil, UserService userService, ApiErrorWriter errorWriter) {
        this.delegationJwtUtil = delegationJwtUtil;
        this.userService = userService;
        this.errorWriter = errorWriter;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ")) {
            filterChain.doFilter(request, response);
            return;
        }
        String token = header.substring(7);
        if (!delegationJwtUtil.isDelegationCandidate(token)) {
            filterChain.doFilter(request, response);
            return;
        }
        try {
            Claims claims = delegationJwtUtil.validate(token);
            String employeeId = claims.get("employee_id", String.class);
            User user = userService.findByEmployeeId(employeeId)
                    .orElseThrow(() -> new DelegationAuthenticationException("Delegation employee is unavailable"));
            if (!user.isEnabled() || !user.isAccountNonExpired() || !user.isAccountNonLocked() || !user.isCredentialsNonExpired()) {
                throw new DelegationAuthenticationException("Delegation employee is not active");
            }
            UsernamePasswordAuthenticationToken authentication = new UsernamePasswordAuthenticationToken(
                    user, null, user.getAuthorities());
            authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
            SecurityContextHolder.getContext().setAuthentication(authentication);
            filterChain.doFilter(request, response);
        } catch (DelegationAuthenticationException exception) {
            SecurityContextHolder.clearContext();
            errorWriter.write(request, response, HttpStatus.UNAUTHORIZED, "DELEGATION_TOKEN_INVALID", "Delegation authentication failed");
        }
    }
}
