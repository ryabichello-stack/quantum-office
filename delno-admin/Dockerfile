FROM node:22-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_DELNO_API_URL=https://api.dlno.ru
ENV NEXT_PUBLIC_DELNO_API_URL=${NEXT_PUBLIC_DELNO_API_URL}
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM node:22-alpine AS production
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
EXPOSE 3000
CMD ["npm", "start", "--", "-p", "3000"]
