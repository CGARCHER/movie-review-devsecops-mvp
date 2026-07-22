package security.fixtures;

/** Fixture vulnerable: no se compila ni se incluye en la imagen. */
final class VulnerableMovieSearch {

    void runTool(String userInput) throws Exception {
        Runtime.getRuntime().exec("movie-tool " + userInput);
    }
}
