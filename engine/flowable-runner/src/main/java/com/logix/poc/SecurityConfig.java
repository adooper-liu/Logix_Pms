package com.logix.poc;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration
class SecurityConfig {
    static void validateToken(String token) {
        if (token == null || token.isBlank() || token.length() < 32) {
            throw new IllegalStateException("Dedicated POC token must contain at least 32 characters");
        }
    }

    @Bean SecurityFilterChain security(HttpSecurity http, @Value("${poc.token}") String token,
            @Value("${sandbox.enabled:false}") boolean sandboxEnabled, @Value("${sandbox.token:}") String sandboxToken) throws Exception {
        validateToken(token);
        if (sandboxEnabled) { validateToken(sandboxToken); if (token.equals(sandboxToken)) throw new IllegalStateException("Separate sandbox token required"); }
        var filter = new OncePerRequestFilter() {
            @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain)
                    throws ServletException, IOException {
                boolean sandbox = req.getRequestURI().startsWith("/sandbox/");
                if (sandbox && !sandboxEnabled) { res.setStatus(404); res.getWriter().write("{\"error\":\"sandbox disabled\"}"); return; }
                String expected = sandbox ? sandboxToken : token;
                String actual = req.getHeader("Authorization");
                if (actual == null || !MessageDigest.isEqual(("Bearer " + expected).getBytes(StandardCharsets.UTF_8), actual.getBytes(StandardCharsets.UTF_8))) {
                    res.setStatus(401); res.setContentType("application/json"); res.getWriter().write("{\"error\":\"unauthorized\"}"); return;
                }
                SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken("poc-machine", null, List.of()));
                chain.doFilter(req, res);
            }
        };
        return http.csrf(c -> c.disable()).cors(c -> c.disable())
            .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .formLogin(f -> f.disable()).httpBasic(b -> b.disable()).logout(l -> l.disable())
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class).build();
    }
}
