import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import Cities from './views/Cities.vue'
import BusinessEntities from './views/BusinessEntities.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: Home },
    { path: '/cities', name: 'cities', component: Cities },
    {
      path: '/business-entities',
      name: 'business-entities',
      component: BusinessEntities,
      meta: { wide: true },
    },
  ],
})
