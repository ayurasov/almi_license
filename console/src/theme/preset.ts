// Brand theme of the console: the red of АльтерОфис (#E41C1C) on neutral grey surfaces, after the
// interfaces of АЭксперт and АльтерОфис (console/docs/design.md).
import { definePreset } from '@primeuix/themes'
import Aura from '@primeuix/themes/aura'

const red = {
  50: '#fef2f2',
  100: '#fde3e3',
  200: '#fbcaca',
  300: '#f6a3a3',
  400: '#ee6a6a',
  500: '#e41c1c',
  600: '#c91515',
  700: '#a81414',
  800: '#8b1616',
  900: '#741818',
  950: '#3f0808',
}

const grey = {
  0: '#ffffff',
  50: '#f7f7f8',
  100: '#f1f1f3',
  200: '#e4e4e7',
  300: '#d4d4d8',
  400: '#a1a1aa',
  500: '#71717a',
  600: '#52525b',
  700: '#3f3f46',
  800: '#27272a',
  900: '#18181b',
  950: '#0c0c0e',
}

export const BrandPreset = definePreset(Aura, {
  semantic: {
    primary: red,
    colorScheme: {
      light: {
        surface: grey,
        text: { color: '{surface.800}', hoverColor: '{surface.900}', mutedColor: '{surface.500}', hoverMutedColor: '{surface.600}' },
        primary: { color: '{primary.500}', contrastColor: '#ffffff', hoverColor: '{primary.600}', activeColor: '{primary.700}' },
        highlight: {
          background: '{primary.50}',
          focusBackground: '{primary.100}',
          color: '{primary.600}',
          focusColor: '{primary.700}',
        },
      },
      dark: {
        surface: grey,
        primary: { color: '{primary.400}', contrastColor: '{surface.950}', hoverColor: '{primary.300}', activeColor: '{primary.200}' },
        highlight: {
          background: 'color-mix(in srgb, {primary.400}, transparent 84%)',
          focusBackground: 'color-mix(in srgb, {primary.400}, transparent 76%)',
          color: 'rgba(255,255,255,.87)',
          focusColor: 'rgba(255,255,255,.87)',
        },
      },
    },
  },
})
