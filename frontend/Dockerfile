FROM node:22-alpine AS base

ENV TZ=America/Bogota
# Next.js manda telemetría anónima a Vercel: apagada en el build y al servir.
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

RUN apk add --no-cache tzdata

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 3000


# Desarrollo: el código llega montado por volumen.
FROM base AS dev
CMD ["npm", "run", "dev"]


# Producción: se compila dentro de la imagen.
FROM base AS runtime
ENV NODE_ENV=production
RUN npm run build
# El build corre como root: `.next` quedaría de root y `node` no podría escribir su caché.
RUN chown -R node:node .next
USER node
CMD ["npm", "run", "start"]
