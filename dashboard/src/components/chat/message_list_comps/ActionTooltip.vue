<template>
  <!-- Hover hint for a message action: a short name and what it does. -->
  <v-tooltip
    activator="parent"
    location="top"
    :open-delay="300"
    content-class="action-tooltip"
  >
    <div class="action-tooltip-title">{{ title }}</div>
    <div v-if="description" class="action-tooltip-description">
      {{ description }}
    </div>
  </v-tooltip>
</template>

<script setup lang="ts">
defineProps<{ title: string; description?: string }>();
</script>

<!-- Not scoped: the tooltip renders in an overlay outside this component.
     A solid dark card stays crisp in both themes (Vuetify's default is a
     translucent grey that looks washed out on dark backgrounds). -->
<style>
.v-tooltip > .v-overlay__content.action-tooltip {
  max-width: 220px;
  padding: 6px 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: #262626;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.28);
  color: #fff;
  line-height: 1.4;
  opacity: 1;
}

.action-tooltip-title {
  font-size: 0.78rem;
  font-weight: 600;
}

.action-tooltip-description {
  margin-top: 1px;
  font-size: 0.72rem;
  color: rgba(255, 255, 255, 0.62);
}
</style>
