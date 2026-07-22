package es.cipriano.tfm.movies.api;

import java.time.Instant;

public record MovieResponse(
        Long id,
        String title,
        Integer releaseYear,
        String genre,
        Instant createdAt,
        long reviewCount,
        Double averageRating) {
}
