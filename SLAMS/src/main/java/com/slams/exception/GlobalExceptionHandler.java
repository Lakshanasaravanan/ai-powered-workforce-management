package com.slams.exception;

import com.slams.dto.ApiErrorResponse;
import com.slams.security.RequestIdFilter;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.Instant;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private ApiErrorResponse error(HttpServletRequest request, String code, String message) {
        return new ApiErrorResponse(code, message, (String) request.getAttribute(RequestIdFilter.ATTRIBUTE), Instant.now());
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ApiErrorResponse> handleNotFound(ResourceNotFoundException ex, HttpServletRequest request) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error(request, "RESOURCE_NOT_FOUND", ex.getMessage()));
    }

    @ExceptionHandler(BusinessRuleConflictException.class)
    public ResponseEntity<ApiErrorResponse> handleConflict(BusinessRuleConflictException ex, HttpServletRequest request) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(error(request, ex.getCode(), ex.getMessage()));
    }

    @ExceptionHandler(MutationRequestValidationException.class)
    public ResponseEntity<ApiErrorResponse> handleMutationValidation(MutationRequestValidationException ex, HttpServletRequest request) {
        return ResponseEntity.badRequest().body(error(request, ex.getCode(), ex.getMessage()));
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<ApiErrorResponse> handleAccessDenied(AccessDeniedException ex, HttpServletRequest request) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(error(request, "FORBIDDEN", "You are not permitted to access this resource"));
    }

    @ExceptionHandler(RuntimeException.class)
    public ResponseEntity<ApiErrorResponse> handleRuntimeException(RuntimeException ex, HttpServletRequest request) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(error(request, "INTERNAL_ERROR", "An unexpected server error occurred"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiErrorResponse> handleValidationExceptions(MethodArgumentNotValidException ex, HttpServletRequest request) {
        return ResponseEntity.badRequest().body(error(request, "VALIDATION_ERROR", "Request validation failed"));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiErrorResponse> handleGeneralException(Exception ex, HttpServletRequest request) {
        return ResponseEntity.internalServerError().body(error(request, "INTERNAL_ERROR", "An unexpected server error occurred"));
    }
}
