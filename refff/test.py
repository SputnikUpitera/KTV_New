a = ["a", "b", "c", "d", "e"]
for item in a[:]:
    print(item)
    if item == "b":
        a.remove(item)
print(a)