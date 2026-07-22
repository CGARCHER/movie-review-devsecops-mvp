package es.cipriano.tfm.movies;

import es.cipriano.tfm.movies.movie.MovieRepository;
import es.cipriano.tfm.movies.review.ReviewRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MovieApiTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ReviewRepository reviewRepository;

    @Autowired
    private MovieRepository movieRepository;

    @BeforeEach
    void cleanDatabase() {
        reviewRepository.deleteAll();
        movieRepository.deleteAll();
    }

    @Test
    void createsMovieAndReview() throws Exception {
        String location = mockMvc.perform(post("/api/movies")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Alien","releaseYear":1979,"genre":"Ciencia ficcion"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("Alien"))
                .andReturn().getResponse().getHeader("Location");

        String movieId = location.substring(location.lastIndexOf('/') + 1);
        mockMvc.perform(post("/api/movies/{id}/reviews", movieId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"author":"Cipriano","rating":5,"comment":"Una pelicula excelente"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.rating").value(5));

        mockMvc.perform(get("/api/movies/{id}", movieId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reviewCount").value(1))
                .andExpect(jsonPath("$.averageRating").value(5.0));
    }

    @Test
    void rejectsInvalidRating() throws Exception {
        String location = mockMvc.perform(post("/api/movies")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Alien","releaseYear":1979,"genre":"Ciencia ficcion"}
                                """))
                .andReturn().getResponse().getHeader("Location");
        String movieId = location.substring(location.lastIndexOf('/') + 1);

        mockMvc.perform(post("/api/movies/{id}/reviews", movieId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"author":"Cipriano","rating":8,"comment":"Puntuacion incorrecta"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields.rating").exists());
    }
}
