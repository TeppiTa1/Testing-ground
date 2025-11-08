circumference = float(input("What is the circumference of your wheel in millimetres? \n"))
revolution = float(input("How many wheel revolutions have taken place in your journey? \n"))
time = float(input("How many minutes did you cycle for? \n")) / 60
distance = round(((circumference * revolution) / 1000000),2)
print(f"You covered {distance} km.")
print(f"At an average speed of {round((distance/time),2)} km/h")