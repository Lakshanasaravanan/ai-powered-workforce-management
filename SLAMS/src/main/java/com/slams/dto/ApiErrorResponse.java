package com.slams.dto;

import java.time.Instant;

public record ApiErrorResponse(String code, String message, String requestId, Instant timestamp) {
}
