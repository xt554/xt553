FROM node:22-bookworm-slim

ENV NODE_ENV=production
WORKDIR /app
COPY signer-node/package.json ./package.json
RUN npm install --omit=dev --ignore-scripts && npm cache clean --force
COPY signer-node/server.js ./server.js
RUN useradd --system --uid 10001 --create-home signer \
    && mkdir -p /var/lib/ton-signer /run/secrets/ton-wallets \
    && chown -R signer:signer /app /var/lib/ton-signer
USER signer
EXPOSE 9000
CMD ["node", "server.js"]
