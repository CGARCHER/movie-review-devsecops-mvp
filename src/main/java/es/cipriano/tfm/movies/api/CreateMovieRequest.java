package es.cipriano.tfm.movies.api;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateMovieRequest(
        @NotBlank @Size(max = 150) String title,
        @NotNull @Min(1888) @Max(2100) Integer releaseYear,
        @NotBlank @Size(max = 60) String genre) {
}
