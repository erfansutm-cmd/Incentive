# ---- base: install deps + copy source ----
FROM node:22-alpine AS base
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .

# ---- dev: Vite dev server with hot reload ----
FROM base AS dev
EXPOSE 5173
CMD ["npm", "run", "dev"]

# ---- build: produce static assets ----
FROM base AS build
RUN npm run build

# ---- prod: serve static build with nginx ----
FROM nginx:alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
