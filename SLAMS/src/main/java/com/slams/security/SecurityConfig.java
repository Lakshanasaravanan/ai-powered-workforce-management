package com.slams.security;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.HeadersConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthFilter;
    private final DelegationAuthenticationFilter delegationAuthenticationFilter;
    private final RequestIdFilter requestIdFilter;
    private final ApiErrorWriter apiErrorWriter;

    @Autowired
    private PasswordEncoder passwordEncoder;

    public SecurityConfig(
            JwtAuthenticationFilter jwtAuthFilter,
            DelegationAuthenticationFilter delegationAuthenticationFilter,
            RequestIdFilter requestIdFilter,
            ApiErrorWriter apiErrorWriter
    ) {
        this.jwtAuthFilter = jwtAuthFilter;
        this.delegationAuthenticationFilter = delegationAuthenticationFilter;
        this.requestIdFilter = requestIdFilter;
        this.apiErrorWriter = apiErrorWriter;
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http,
                                                   UserDetailsService userDetailsService) throws Exception {

        http
                // CSRF disabled because login is handled via API + JWT cookie
                .csrf(csrf -> csrf.disable())

                // We are using JWT cookie, so keep stateless
                .sessionManagement(session ->
                        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
                )

                // Public routes
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/login",
                                "/register",
                                "/api/auth/**",
                                "/css/**",
                                "/js/**",
                                "/images/**",
                                "/favicon.ico",
                                "/h2-console/**",
                                "/error"
                        ).permitAll()
                        .anyRequest().authenticated()
                )

                // H2 console support
                .headers(headers ->
                        headers.frameOptions(HeadersConfigurer.FrameOptionsConfig::sameOrigin)
                )

                // If not authenticated:
                // - browser page request -> send to /login
                // - api request -> 401
                .exceptionHandling(exceptions -> exceptions.authenticationEntryPoint((request, response, authException) -> {
                    String uri = request.getRequestURI();

                    // Never redirect /login again, just allow it to render
                    if ("/login".equals(uri)) {
                        response.setStatus(HttpServletResponse.SC_OK);
                        request.getRequestDispatcher("/login").forward(request, response);
                        return;
                    }

                    String accept = request.getHeader("Accept");
                    boolean isHtmlRequest = accept != null && accept.contains("text/html");
                    boolean isApiRequest = uri.startsWith("/api/");

                    if (isApiRequest) {
                        apiErrorWriter.write(request, response, org.springframework.http.HttpStatus.UNAUTHORIZED,
                                "UNAUTHENTICATED", "Authentication is required");
                    } else if (isHtmlRequest) {
                        response.sendRedirect("/login");
                    } else {
                        response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Unauthorized");
                    }
                })
                        .accessDeniedHandler((request, response, exception) ->
                                apiErrorWriter.write(request, response, org.springframework.http.HttpStatus.FORBIDDEN,
                                        "FORBIDDEN", "You are not permitted to access this resource")))

                // Logout clears JWT cookie
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .deleteCookies("JWT")
                        .clearAuthentication(true)
                        .invalidateHttpSession(true)
                        .logoutSuccessHandler((request, response, authentication) -> {
                            jakarta.servlet.http.Cookie cookie = new jakarta.servlet.http.Cookie("JWT", "");
                            cookie.setPath("/");
                            cookie.setHttpOnly(true);
                            cookie.setMaxAge(0);
                            response.addCookie(cookie);
                            response.sendRedirect("/login?logout");
                        })
                )

                .authenticationProvider(authenticationProvider(userDetailsService))

                // Registration order is intentional: request ID, RS256 delegation, then normal HS256 JWT.
                // All are positioned before Spring's standard username/password filter.
                .addFilterBefore(requestIdFilter, UsernamePasswordAuthenticationFilter.class)
                .addFilterBefore(delegationAuthenticationFilter, UsernamePasswordAuthenticationFilter.class)
                .addFilterBefore(jwtAuthFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    public AuthenticationProvider authenticationProvider(UserDetailsService userDetailsService) {
        DaoAuthenticationProvider authProvider = new DaoAuthenticationProvider();
        authProvider.setUserDetailsService(userDetailsService);
        authProvider.setPasswordEncoder(passwordEncoder);
        return authProvider;
    }

    @Bean
    public AuthenticationManager authenticationManager(AuthenticationConfiguration config) throws Exception {
        return config.getAuthenticationManager();
    }
}
