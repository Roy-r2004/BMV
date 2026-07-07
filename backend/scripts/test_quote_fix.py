from app.application.preview_app.safety import fix_unescaped_apostrophes

sample = "  text: 'Fixing just one station's over-portioning saved us $1,200/month in ingredient costs.',"
fixed, changed = fix_unescaped_apostrophes(sample)
print("changed:", changed)
print(fixed)
