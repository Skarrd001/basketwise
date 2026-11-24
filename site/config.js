// Public settings for optional sign-in. Both values are designed to be public (they sit in every
// visitor's browser); the database's Row Level Security is what protects users' data.
// Leave them empty and the app works exactly as before, with no account features shown.
window.BW_CONFIG = {
  supabaseUrl: "",       // e.g. "https://abcdefghijklmnop.supabase.co"
  supabaseAnonKey: "",   // the project's anon / publishable key
  googleSignIn: false,   // set true once Google is enabled in Supabase -> Authentication -> Providers
};
