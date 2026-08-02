FROM nginx:1.29-alpine

COPY docker/security-dashboard/nginx.conf /etc/nginx/nginx.conf
COPY dashboard/ /usr/share/nginx/html/

RUN mkdir -p /usr/share/nginx/html/reports \
    && chown -R nginx:nginx /usr/share/nginx/html

USER nginx
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
