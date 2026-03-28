# Build
FROM node:20-alpine AS builder

ARG VITE_AVAILABLE_MODELS
ENV VITE_AVAILABLE_MODELS=$VITE_AVAILABLE_MODELS

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build-only

# Serve
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]