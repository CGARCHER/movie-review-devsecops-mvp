package es.cipriano.tfm.movies.api;

import java.time.Instant;

public record ReviewResponse(
        Long id,
        Long movieId,
        String author,
        Integer rating,
        String comment,
        Instant createdAt) {
}
