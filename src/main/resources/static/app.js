const moviesContainer = document.querySelector('#movies');
const movieForm = document.querySelector('#movie-form');
const movieMessage = document.querySelector('#movie-message');
const template = document.querySelector('#movie-template');

async function request(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
    });
    const body = response.status === 204 ? null : await response.json();
    if (!response.ok) throw new Error(body?.message || 'No se ha podido completar la operación');
    return body;
}

async function loadMovies() {
    moviesContainer.replaceChildren();
    const movies = await request('/api/movies');
    if (movies.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'empty';
        empty.textContent = 'Todavía no hay películas. Añade la primera.';
        moviesContainer.append(empty);
        return;
    }
    for (const movie of movies) moviesContainer.append(await renderMovie(movie));
}

async function renderMovie(movie) {
    const fragment = template.content.cloneNode(true);
    const card = fragment.querySelector('.movie-card');
    fragment.querySelector('.title').textContent = movie.title;
    fragment.querySelector('.genre').textContent = movie.genre;
    fragment.querySelector('.year').textContent = movie.releaseYear;
    fragment.querySelector('.rating').textContent = movie.averageRating === null
        ? 'Sin reseñas'
        : `${movie.averageRating.toFixed(1)} / 5 (${movie.reviewCount})`;

    const reviewsElement = fragment.querySelector('.reviews');
    const reviews = await request(`/api/movies/${movie.id}/reviews`);
    for (const review of reviews) {
        const element = document.createElement('div');
        element.className = 'review';
        const heading = document.createElement('strong');
        heading.textContent = `${review.author} · ${review.rating}/5`;
        const comment = document.createElement('p');
        comment.textContent = review.comment;
        element.append(heading, comment);
        reviewsElement.append(element);
    }

    const form = fragment.querySelector('.review-form');
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(form));
        data.rating = Number(data.rating);
        const message = form.querySelector('.message');
        try {
            await request(`/api/movies/${movie.id}/reviews`, { method: 'POST', body: JSON.stringify(data) });
            await loadMovies();
        } catch (error) {
            message.textContent = error.message;
        }
    });
    return card;
}

movieForm.addEventListener('submit', async event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(movieForm));
    data.releaseYear = Number(data.releaseYear);
    movieMessage.textContent = '';
    try {
        await request('/api/movies', { method: 'POST', body: JSON.stringify(data) });
        movieForm.reset();
        await loadMovies();
    } catch (error) {
        movieMessage.textContent = error.message;
    }
});

document.querySelector('#reload').addEventListener('click', loadMovies);
loadMovies().catch(error => { moviesContainer.textContent = error.message; });
