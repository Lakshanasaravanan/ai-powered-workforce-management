package com.slams.security;

public class DelegationAuthenticationException extends RuntimeException {
    public DelegationAuthenticationException(String message) {
        super(message);
    }

    public DelegationAuthenticationException(String message, Throwable cause) {
        super(message, cause);
    }
}
