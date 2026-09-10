package com.slams.exception;

public class BusinessRuleConflictException extends RuntimeException {
    public BusinessRuleConflictException(String message) {
        super(message);
    }
}
