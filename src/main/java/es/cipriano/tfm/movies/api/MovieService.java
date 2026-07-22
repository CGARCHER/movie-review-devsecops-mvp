package es.cipriano.tfm.movies.api;

import es.cipriano.tfm.movies.movie.Movie;
import es.cipriano.tfm.movies.movie.MovieRepository;
import es.cipriano.tfm.movies.review.Review;
import es.cipriano.tfm.movies.review.ReviewRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@Transactional(readOnly = true)
public class MovieService {

    private final MovieRepository movieRepository;
    private final ReviewRepository reviewRepository;

    public MovieService(MovieRepository movieRepository, ReviewRepository reviewRepository) {
        this.movieRepository = movieRepository;
        this.reviewRepository = reviewRepository;
    }

    public List<MovieResponse> findMovies() {
        return movieRepository.findAllByOrderByCreatedAtDesc().stream()
                .map(this::toMovieResponse)
                .toList();
    }

    public MovieResponse findMovie(long id) {
        return toMovieResponse(requireMovie(id));
    }

    @Transactional
    public MovieResponse createMovie(CreateMovieRequest request) {
        Movie movie = new Movie(request.title().strip(), request.releaseYear(), request.genre().strip());
        return toMovieResponse(movieRepository.save(movie));
    }

    public List<ReviewResponse> findReviews(long movieId) {
        requireMovie(movieId);
        return reviewRepository.findByMovieIdOrderByCreatedAtDesc(movieId).stream()
                .map(this::toReviewResponse)
                .toList();
    }

    @Transactional
    public ReviewResponse createReview(long movieId, CreateReviewRequest request) {
        Movie movie = requireMovie(movieId);
        Review review = new Review(
                movie,
                request.author().strip(),
                request.rating(),
                request.comment().strip());
        return toReviewResponse(reviewRepository.save(review));
    }

    private Movie requireMovie(long id) {
        return movieRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("No existe la pelicula " + id));
    }

    private MovieResponse toMovieResponse(Movie movie) {
        List<Review> reviews = reviewRepository.findByMovieIdOrderByCreatedAtDesc(movie.getId());
        Double average = reviews.isEmpty()
                ? null
                : reviews.stream().mapToInt(Review::getRating).average().orElse(0.0);
        return new MovieResponse(
                movie.getId(),
                movie.getTitle(),
                movie.getReleaseYear(),
                movie.getGenre(),
                movie.getCreatedAt(),
                reviews.size(),
                average);
    }

    private ReviewResponse toReviewResponse(Review review) {
        return new ReviewResponse(
                review.getId(),
                review.getMovie().getId(),
                review.getAuthor(),
                review.getRating(),
                review.getComment(),
                review.getCreatedAt());
    }
}
