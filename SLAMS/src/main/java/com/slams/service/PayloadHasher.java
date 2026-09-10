package com.slams.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

final class PayloadHasher {
    private PayloadHasher() { }
    static String sha256(String canonicalPayload) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(canonicalPayload.getBytes(StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(digest);
        } catch (Exception exception) { throw new IllegalStateException("Unable to hash request", exception); }
    }
}
