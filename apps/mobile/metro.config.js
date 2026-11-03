// expo-sqlite on web runs wa-sqlite (WebAssembly) in a worker with SharedArrayBuffer, which needs the
// .wasm asset bundled and the page served cross-origin isolated (COOP/COEP) by the dev server.
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

config.resolver.assetExts.push('wasm');

const enhance = config.server.enhanceMiddleware;
config.server.enhanceMiddleware = (middleware, server) => {
  const inner = enhance ? enhance(middleware, server) : middleware;
  return (req, res, next) => {
    res.setHeader('Cross-Origin-Embedder-Policy', 'credentialless');
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    return inner(req, res, next);
  };
};

module.exports = config;
