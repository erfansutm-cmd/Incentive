import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import Cities from './views/Cities.vue'
import BusinessEntities from './views/BusinessEntities.vue'
import PlanDetail from './views/PlanDetail.vue'
import DecisionMatrix from './views/DecisionMatrix.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: Home },
    { path: '/cities', name: 'cities', component: Cities },
    { path: '/plans/:id', name: 'plan-detail', component: PlanDetail },
    {
      path: '/decision-matrix',
      name: 'decision-matrix',
      component: DecisionMatrix,
      meta: { wide: true },
    },
    {
      // Focused view of a single incentive type: same component and UI as the
      // main Decision Matrix tab, scoped via ?city_group=…&type=….
      path: '/decision-matrix/type',
      name: 'decision-matrix-type',
      component: DecisionMatrix,
      meta: { wide: true },
    },
    {
      path: '/business-entities',
      name: 'business-entities',
      component: BusinessEntities,
      meta: { wide: true },
    },
  ],
})
