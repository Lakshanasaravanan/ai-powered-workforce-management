package com.slams.exception;
public class MutationRequestValidationException extends RuntimeException {
    private final String code;
    public MutationRequestValidationException(String code, String message) { super(message); this.code = code; }
    public String getCode() { return code; }
}
