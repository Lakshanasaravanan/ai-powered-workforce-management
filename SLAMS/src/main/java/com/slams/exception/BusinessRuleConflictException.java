package com.slams.exception;

public class BusinessRuleConflictException extends RuntimeException {
    private final String code;
    public BusinessRuleConflictException(String message) {
        this("BUSINESS_RULE_CONFLICT", message);
    }
    public BusinessRuleConflictException(String code, String message) { super(message); this.code = code; }
    public String getCode() { return code; }
}
