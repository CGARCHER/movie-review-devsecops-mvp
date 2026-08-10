package security.fixtures;

import java.security.MessageDigest;

/** Fixture vulnerable: no se compila ni se incluye en la imagen. */
final class VulnerableMovieSearch {

    private static final String API_KEY = "demo-insecure-api-key-12345";

    void runTool(String userInput) throws Exception {
        Runtime.getRuntime().exec("movie-tool " + userInput);
    }

    byte[] insecureDigest(String movieTitle) throws Exception {
        return MessageDigest.getInstance("MD5").digest(movieTitle.getBytes());
    }
}
