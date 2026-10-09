FROM node:22-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_BASE_PATH=
ARG NEXT_PUBLIC_YM_COUNTER_ID=
ARG NEXT_PUBLIC_SITE_URL=https://dlno.ru
ARG NEXT_PUBLIC_YANDEX_VERIFICATION=
ENV NEXT_PUBLIC_BASE_PATH=${NEXT_PUBLIC_BASE_PATH}
ENV NEXT_PUBLIC_YM_COUNTER_ID=${NEXT_PUBLIC_YM_COUNTER_ID}
ENV NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL}
ENV NEXT_PUBLIC_YANDEX_VERIFICATION=${NEXT_PUBLIC_YANDEX_VERIFICATION}
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build:node

FROM node:22-alpine AS production
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["npm", "run", "start:node"]
