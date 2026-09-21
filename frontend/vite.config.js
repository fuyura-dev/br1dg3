import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    // ITO ANG FIX: Pipilitin nito ang Vite na gumamit ng iisang React lang
    dedupe: ['react', 'react-dom'], 
  },
})