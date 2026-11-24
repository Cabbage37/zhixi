import {build} from 'esbuild';
await build({entryPoints:[new URL('./index.jsx',import.meta.url).pathname.replace(/^\/([A-Z]:)/,'$1')].map(decodeURIComponent),bundle:true,minify:true,outfile:'web/assets/workshop-chat.js',define:{'process.env.NODE_ENV':'"production"'},loader:{'.woff':'dataurl','.woff2':'dataurl','.ttf':'dataurl'}})
