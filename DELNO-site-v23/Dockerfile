FROM node:22-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_BASE_PATH=
ARG NEXT_PUBLIC_DELNO_WIDGET_SITE_KEY=demo_dlno
ENV NEXT_PUBLIC_BASE_PATH=${NEXT_PUBLIC_BASE_PATH}
ENV NEXT_PUBLIC_DELNO_WIDGET_SITE_KEY=${NEXT_PUBLIC_DELNO_WIDGET_SITE_KEY}
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build:node

FROM node:22-alpine AS production
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/package.json ./
COPY --from=build /app/package-lock.json* ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["npm", "run", "start:node"]
