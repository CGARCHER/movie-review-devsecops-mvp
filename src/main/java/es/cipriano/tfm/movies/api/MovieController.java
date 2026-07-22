package es.cipriano.tfm.movies.api;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.util.List;

@RestController
@RequestMapping("/api/movies")
public class MovieController {

    private final MovieService service;

    public MovieController(MovieService service) {
        this.service = service;
    }

    @GetMapping
    public List<MovieResponse> findMovies() {
        return service.findMovies();
    }

    @GetMapping("/{id}")
    public MovieResponse findMovie(@PathVariable long id) {
        return service.findMovie(id);
    }

    @PostMapping
    public ResponseEntity<MovieResponse> createMovie(@Valid @RequestBody CreateMovieRequest request) {
        MovieResponse movie = service.createMovie(request);
        return ResponseEntity.created(URI.create("/api/movies/" + movie.id())).body(movie);
    }

    @GetMapping("/{id}/reviews")
    public List<ReviewResponse> findReviews(@PathVariable long id) {
        return service.findReviews(id);
    }

    @PostMapping("/{id}/reviews")
    public ResponseEntity<ReviewResponse> createReview(
            @PathVariable long id,
            @Valid @RequestBody CreateReviewRequest request) {
        ReviewResponse review = service.createReview(id, request);
        return ResponseEntity.created(URI.create("/api/movies/" + id + "/reviews/" + review.id())).body(review);
    }
}
