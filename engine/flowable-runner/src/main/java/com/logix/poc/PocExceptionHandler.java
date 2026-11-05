package com.logix.poc;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

class PocException extends RuntimeException {
    private final int status;
    PocException(int status, String message) { super(message); this.status = status; }
    int status() { return status; }
}

@RestControllerAdvice
class PocExceptionHandler {
    @ExceptionHandler(PocException.class) ResponseEntity<?> domain(PocException ex) {
        return ResponseEntity.status(ex.status()).body(Map.of("error", ex.getMessage()));
    }
    @ExceptionHandler({org.springframework.http.converter.HttpMessageNotReadableException.class,
            org.springframework.web.method.annotation.MethodArgumentTypeMismatchException.class})
    ResponseEntity<?> malformed(Exception ex) { return ResponseEntity.badRequest().body(Map.of("error", "Invalid request")); }
    @ExceptionHandler(Exception.class) ResponseEntity<?> unexpected(Exception ex) {
        return ResponseEntity.status(503).body(Map.of("error", "Operation unavailable; query original command before retry"));
    }
}
