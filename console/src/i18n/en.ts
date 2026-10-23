import type ru from './ru'

const en: typeof ru = {
  app: { title: 'ALMI licensing', signOut: 'Sign out' },
  menu: {
    customers: 'Customers',
    licenses: 'Licenses',
    activations: 'Activations',
    catalog: 'Catalog',
    profiles: 'Profiles',
    import: 'Import',
    stats: 'Statistics',
    audit: 'Audit log',
    users: 'Users',
  },
  placeholder: 'This section comes in later iterations.',
  login: { title: 'Console sign-in', username: 'User name', password: 'Password', submit: 'Sign in' },
  errors: {
    network: 'The server is unreachable. Check the connection and try again.',
    unknown: 'The operation failed. Try again later.',
    retry: 'Retry',
  },
  customers: {
    title: 'Customers',
    create: 'New customer',
    edit: 'Edit',
    empty: 'No customers. Create the first one or change the filters.',
    filters: { name: 'Name', inn: 'INN', status: 'Status', any: 'Any' },
    columns: { name: 'Name', inn: 'INN', externalId: 'LK ID', status: 'Status', createdAt: 'Created' },
    status: { active: 'Active', archived: 'Archived' },
    form: {
      titleCreate: 'New customer',
      titleEdit: 'Customer',
      name: 'Name',
      inn: 'INN',
      externalId: 'LK identifier',
      status: 'Status',
      save: 'Save',
      cancel: 'Cancel',
    },
    saved: 'Customer saved',
    errors: {
      nameRequired: 'Enter the name.',
      innInvalid: 'Invalid INN: 10 or 12 digits with a valid check digit.',
    },
  },
}

export default en
